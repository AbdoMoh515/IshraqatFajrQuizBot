import logging
import fitz
import re
import asyncio
import os
from io import BytesIO
from typing import List, Dict, Set, Any, Tuple, Optional, Union
from aiogram import Bot
from aiogram.types import Poll, Message, FSInputFile

logger = logging.getLogger(__name__)

async def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from PDF file with optimized formatting preservation.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Extracted text with preserved formatting
    """
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            page_count = len(doc)
            if page_count == 0:
                logger.warning("PDF is empty: no pages found")
                return ""
                
            logger.info(f"Processing PDF with {page_count} pages")
            
            for page_num, page in enumerate(doc):
                try:
                    # Get text with better formatting
                    page_text = page.get_text("text")
                    # Clean up excessive whitespace while preserving format
                    page_text = re.sub(r' +', ' ', page_text)
                    page_text = re.sub(r'\n\s*\n', '\n\n', page_text)
                    
                    text += page_text + "\n\n"
                except Exception as e:
                    logger.error(f"Error extracting text from page {page_num+1}: {str(e)}")
    except Exception as e:
        logger.error(f"Error opening PDF file: {str(e)}")
    
    return text

async def extract_text_from_file(file_path: str) -> str:
    """
    Extract text from a file (PDF or text file)
    
    Args:
        file_path: Path to the file
        
    Returns:
        Extracted text
    """
    try:
        if file_path.lower().endswith('.pdf'):
            return await extract_text_from_pdf(file_path)
        else:
            # Assume it's a text file
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        logger.error(f"Error extracting text from file: {str(e)}", exc_info=True)
        return ""

def extract_questions_from_text(text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """Extract questions and answers from text using a robust, multi-stage approach.

    Args:
        text: The text extracted from the file.

    Returns:
        A tuple containing:
        - A list of successfully parsed question dictionaries.
        - A list of dictionaries for skipped questions, including the reason for skipping.
    """
    text = text.replace('\r\n', '\n').strip()
    logger.info(f"Total length of extracted text: {len(text)} characters")

    questions = []
    skipped_questions = []
    extracted_question_texts = set()

    # Split text into blocks based on question numbering. This is more reliable.
    question_blocks = re.split(r'\n(?=\s*(?:Q\s*)?\d+\s*[.\-)])', text)
    logger.info(f"Found {len(question_blocks)} potential question blocks.")

    for i, block in enumerate(question_blocks):
        block = block.strip()
        if not block:
            continue

        try:
            # 1. Extract Question Number and Text (up to the first option)
            q_match = re.match(r'(?:Q\s*)?(\d+)\s*[.\-)]\s*(.*?)(?=\n\s*[a-zA-Z][.)])', block, re.DOTALL)
            if not q_match:
                logger.warning(f"Skipping block {i+1}: No question pattern matched. Content: {block[:200]}...")
                skipped_questions.append({'number': f'Block {i+1}', 'reason': 'Could not find question number or text.'})
                continue

            question_num = q_match.group(1)
            question_text = q_match.group(2).strip().replace('\n', ' ')

            if not question_text:
                skipped_questions.append({'number': question_num, 'reason': 'Empty question text.'})
                continue

            if question_text in extracted_question_texts:
                skipped_questions.append({'number': question_num, 'reason': 'Duplicate question.'})
                continue

            # 2. Extract Answer (must exist)
            answer_match = re.search(r'Answer\s*:\s*([a-zA-Z])', block, re.IGNORECASE)
            if not answer_match:
                logger.warning(f"Skipping Q#{question_num}: No answer line found.")
                skipped_questions.append({'number': question_num, 'reason': 'No answer line found.'})
                continue
            correct_letter = answer_match.group(1).lower()

            # 3. Extract Options (from first option to just before the answer line)
            options_part_match = re.search(r'((?:\n\s*[a-zA-Z][.)].*?)+)(?=\n\s*Answer\s*:)', block, re.DOTALL)
            if not options_part_match:
                logger.warning(f"Skipping Q#{question_num}: Could not find options block before answer.")
                skipped_questions.append({'number': question_num, 'reason': 'No options found.'})
                continue
            
            options_text = options_part_match.group(1)
            option_matches = re.findall(r'\n\s*([a-zA-Z])[.)]\s*(.*?)(?=\n\s*[a-zA-Z][.)]|$)', options_text, re.DOTALL)

            if len(option_matches) < 2:
                logger.warning(f"Skipping Q#{question_num}: Found only {len(option_matches)} options.")
                skipped_questions.append({'number': question_num, 'reason': f'Found only {len(option_matches)} options.'})
                continue

            # 4. Process and Validate
            options = [opt[1].strip().replace('\n', ' ') for opt in option_matches]
            option_letters = [opt[0].lower() for opt in option_matches]
            
            try:
                correct_index = option_letters.index(correct_letter)
            except ValueError:
                logger.warning(f"Skipping Q#{question_num}: Correct answer letter '{correct_letter}' not in options {option_letters}.")
                skipped_questions.append({'number': question_num, 'reason': f'Correct answer letter "{correct_letter}" not in options {option_letters}.'})
                continue

            questions.append({
                'question_num': question_num,
                'question': question_text,
                'options': options,
                'correct_option_id': correct_index
            })
            extracted_question_texts.add(question_text)
            logger.info(f"Successfully parsed question {question_num}: {question_text[:60]}...")

        except Exception as e:
            logger.error(f"Error processing block {i+1}: {e}\nContent: {block[:200]}...", exc_info=True)
            skipped_questions.append({'number': f'Block {i+1}', 'reason': f'An unexpected error occurred: {e}'})

    return questions, skipped_questions

async def send_telegram_quizzes(bot: Bot, questions: List[Dict[str, Any]], chat_id: int, quiz_counter: Dict[int, int]) -> Tuple[int, int, List[str]]:
    """Send questions as Telegram quizzes with sequential numbering.

    Args:
        bot: Telegram bot instance.
        questions: List of question dictionaries.
        chat_id: Chat ID to send quizzes to.
        quiz_counter: A dictionary to track the current quiz number for each user.

    Returns:
        A tuple containing the number of sent quizzes, the number of errors,
        and a list of failed question numbers.
    """
    sent_count = 0
    error_count = 0
    failed_questions = []

    # Get the current question number for this user, default to 1 if not set
    current_question_num = quiz_counter.get(chat_id, 1)

    for q in questions:
        try:
            original_question = q['question']
            
            # Remove any existing numbering to avoid confusion
            unnumbered_question = re.sub(r'^\d+\s*[.)]\s*', '', original_question)
            
            # Add the new sequential number
            numbered_question = f"{current_question_num}. {unnumbered_question}"

            await bot.send_poll(
                chat_id=chat_id,
                question=numbered_question,
                options=q['options'],
                type='quiz',
                correct_option_id=q['correct_option_id'],
                is_anonymous=True,
            )
            sent_count += 1
            current_question_num += 1
            await asyncio.sleep(0.5)  # Avoid flood limits
        except Exception as e:
            logger.error(f"Error sending quiz {q.get('question_num', '?')}: {e}")
            error_count += 1
            failed_questions.append(q.get('question_num', '?'))

    # Update the counter for the user for the next batch
    quiz_counter[chat_id] = current_question_num

    return sent_count, error_count, failed_questions

async def format_quiz_as_text(quiz: Poll, question_num: Optional[int] = None) -> str:
    """
    Convert a single Telegram quiz to text format with clearly marked correct answer
    
    Args:
        quiz: Telegram Poll object
        question_num: Optional question number
        
    Returns:
        Formatted question text
    """
    try:
        prefix = f"{question_num}. " if question_num is not None else ""
        text = f"{prefix}{quiz.question}\n"
        
        # Robustly get correct_option_id (handles 0 as valid)
        correct_option_id = getattr(quiz, 'correct_option_id', None)
        has_correct_answer = correct_option_id is not None
        logger.info(f"Quiz: {getattr(quiz, 'question', '')[:30]}... | correct_option_id: {correct_option_id} | options: {[getattr(opt, 'text', str(opt)) for opt in getattr(quiz, 'options', [])]}")
        
        # Add options with correct answer marked
        for i, option in enumerate(quiz.options):
            option_text = option.text if hasattr(option, 'text') else str(option)
            # Just print the options, no emoji for correct answer
            text += f"{chr(97 + i)}) {option_text}\n"  # a), b), c), d)

        # Add explicit answer line
        if has_correct_answer:
            correct_letter = chr(97 + correct_option_id)
            correct_text = quiz.options[correct_option_id].text if hasattr(quiz.options[correct_option_id], 'text') else str(quiz.options[correct_option_id])
            text += f"Answer: {correct_letter}) {correct_text}"
        else:
            text += "Answer: Not provided"

        return text

    except Exception as e:
        logger.error(f"Error formatting quiz: {e}", exc_info=True)
        return "Error formatting quiz"

def save_questions_to_file(questions: List[str], file_path: str) -> bool:
    """
    Save extracted questions to a text file
    
    Args:
        questions: List of formatted question strings
        file_path: Path to save the file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n\n'.join(questions))
        return True
    except Exception as e:
        logger.error(f"Error saving questions to file: {e}", exc_info=True)
        return False

def get_temp_file_path(user_id: int, prefix: str = "quiz_", suffix: str = ".txt") -> str:
    """Generate a temporary file path for a user.

    Args:
        user_id: User ID.
        prefix: File prefix.
        suffix: File suffix.

    Returns:
        Path to temporary file.
    """
    os.makedirs("temp", exist_ok=True)
    return os.path.join("temp", f"{prefix}{user_id}{suffix}")
