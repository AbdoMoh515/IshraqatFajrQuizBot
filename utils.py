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

def extract_questions_from_text(text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Extract questions and answers from text with flexible format support.
    
    Args:
        text: Text extracted from file
        
    Returns:
        Tuple of (list of questions with options and correct answers, list of skipped question numbers)
    """
    # Clean up text
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'\r\n', '\n', text)  # Normalize line endings
    
    # Log diagnostic info
    logger.info(f"Text extracted (first 500 chars): {text[:500]}...")
    logger.info(f"Total length of extracted text: {len(text)} characters")
    
    questions = []
    extracted_questions: Set[str] = set()
    skipped_questions = []
    
    # Try to extract questions using a more flexible approach
    # First split the text into potential question blocks
    question_blocks = re.split(r'\n\s*\n|\n(?=\d+\.?\s)', text)
    
    logger.info(f"Found {len(question_blocks)} potential question blocks")
    
    for i, block in enumerate(question_blocks):
        try:
            # Skip empty blocks
            if not block.strip():
                continue
                
            # Try to identify if this is a question block
            # Look for options pattern (a), b), c), d), etc.) - support more than just a-d
            options_pattern = re.findall(r'\n[a-z]\)\s*[^\n]+', block, re.IGNORECASE)
            if len(options_pattern) < 2:  # Need at least 2 options
                continue
                
            # Look for answer line - support more options (a-z)
            answer_match = re.search(r'\n(?:\*?Answer|\*?Answers?):\s*([a-zA-Z])', block)
            if not answer_match:
                logger.warning(f"Block {i+1} has options but no answer line: {block[:100]}...")
                skipped_questions.append(str(i+1))
                continue
                
            # Extract question number if present
            question_num_match = re.match(r'^\s*(\d+)[\.\)]?\s*', block)
            question_num = question_num_match.group(1) if question_num_match else str(i+1)
            
            # Extract question text
            if question_num_match:
                # Remove question number from the beginning
                question_text = block[question_num_match.end():].strip()
            else:
                question_text = block.strip()
                
            # Find where options start - support more options (a-z)
            options_start = re.search(r'\n[a-z]\)\s*', question_text, re.IGNORECASE)
            if not options_start:
                logger.warning(f"Cannot find options start in block {i+1}")
                skipped_questions.append(question_num)
                continue
                
            # Split question text and options
            pure_question = question_text[:options_start.start()].strip()
            options_text = question_text[options_start.start():].strip()
            
            # Extract options - support more options (a-z)
            options_matches = re.findall(r'\n([a-z])\)\s*([^\n]+)', '\n' + options_text, re.IGNORECASE)
            if len(options_matches) < 2:
                logger.warning(f"Not enough options found in block {i+1}")
                skipped_questions.append(question_num)
                continue
                
            # Sort options by letter
            options_matches.sort(key=lambda x: x[0])
            
            # Extract options text
            options = [opt[1].strip() for opt in options_matches]
            
            # Get correct answer - normalize to lowercase for consistency
            correct_answer = answer_match.group(1).lower()
            correct_index = ord(correct_answer) - ord('a')
            
            # Ensure correct answer is valid for the options we found
            if correct_index < 0 or correct_index >= len(options_matches):
                logger.warning(f"Question {question_num} has invalid correct answer: {correct_answer}, options count: {len(options_matches)}")
                skipped_questions.append(question_num)
                continue
            
            # Ensure correct answer is within range
            if 0 <= correct_index < len(options):
                # Create unique ID for question
                question_id = pure_question[:50]
                if question_id not in extracted_questions:
                    questions.append({
                        "question_num": question_num,
                        "question": pure_question,
                        "options": options,
                        "correct_option_id": correct_index
                    })
                    extracted_questions.add(question_id)
                    logger.info(f"Added new question {question_num}: {question_id}")
                else:
                    logger.info(f"Skipped duplicate question {question_num}: {question_id}")
            else:
                skipped_questions.append(question_num)
                logger.warning(f"Question {question_num} has invalid correct_index: {correct_index}, options count: {len(options)}")
        except Exception as e:
            skipped_questions.append(str(i+1))
            logger.warning(f"Error extracting question block {i+1}: {str(e)}")
            continue
    
    # If we didn't find any questions with the flexible approach, try the regex patterns
    if not questions:
        logger.info("No questions found with flexible approach, trying regex patterns")
        
        # Patterns for different question formats
        patterns = [
            # Basic pattern with options a) b) c) d) etc. and answer - support more options
            r"(?:(\d+)[-\.]?\s*)?(.*?)\n+([a-z]\)\s*.*?(?:\n[a-z]\)\s*.*?){1,20})\n+(?:\*?Answer|\*?Answers?):\s*([a-z])\)?",
            
            # Pattern with options A) B) C) D) etc. (uppercase) - support more options
            r"(?:(\d+)[-\.]?\s*)?(.*?)\n+([A-Z]\)\s*.*?(?:\n[A-Z]\)\s*.*?){1,20})\n+(?:\*?Answer|\*?Answers?):\s*([A-Z])\)?",
            
            # Pattern with options using dots a. b. c. d. etc. - support more options
            r"(?:(\d+)[-\.]?\s*)?(.*?)\n+([a-z]\.\s*.*?(?:\n[a-z]\.\s*.*?){1,20})\n+(?:\*?Answer|\*?Answers?):\s*([a-z])"
        ]
        
        question_count = 0
        
        # Process each pattern
        for i, pattern in enumerate(patterns):
            matches = re.findall(pattern, text, re.DOTALL)
            logger.info(f"Pattern {i+1}: Found {len(matches)} matches")
            
            for match in matches:
                try:
                    question_count += 1
                    question_num = match[0].strip() if match[0] else str(question_count)
                    question_text = match[1].strip()
                    
                    # Extract all options
                    options_text = match[2].strip()
                    
                    # Extract options based on format - support more options (a-z)
                    if '.' in options_text and not ')' in options_text:  # a. b. c. format
                        options_raw = re.findall(r'([a-zA-Z])\.\s*(.*?)(?=\n[a-zA-Z]\.|$)', options_text, re.DOTALL)
                    else:  # a) b) c) format
                        options_raw = re.findall(r'([a-zA-Z]\))\s*(.*?)(?=\n[a-zA-Z]\)|$)', options_text, re.DOTALL)
                    
                    # Normalize correct answer
                    correct_answer = match[3].strip().lower()
                    if correct_answer.endswith(')'):
                        correct_answer = correct_answer[:-1]
                    correct_index = ord(correct_answer) - ord('a')
                    
                    # Extract option text
                    options = []
                    for opt in options_raw:
                        option_text = opt[1].strip()
                        options.append(option_text)
                    
                    # Ensure correct answer is within range
                    if 0 <= correct_index < len(options):
                        # Create unique ID for question
                        question_id = question_text[:50]
                        if question_id not in extracted_questions:
                            questions.append({
                                "question_num": question_num,
                                "question": question_text,
                                "options": options,
                                "correct_option_id": correct_index
                            })
                            extracted_questions.add(question_id)
                            logger.info(f"Added new question: {question_id}")
                        else:
                            logger.info(f"Skipped duplicate question: {question_id}")
                    else:
                        skipped_questions.append(question_num)
                        logger.warning(f"Question {question_num} has invalid correct_index: {correct_index}, options count: {len(options)}")
                except Exception as e:
                    skipped_questions.append(str(question_count))
                    logger.warning(f"Error extracting question {question_count}: {str(e)}")
                    continue
    
    return questions, skipped_questions

async def send_telegram_quizzes(bot: Bot, questions: List[Dict[str, Any]], chat_id: int) -> Tuple[int, int, List[str]]:
    """
    Send questions as Telegram quizzes with sequential numbering
    
    Args:
        bot: Telegram bot instance
        questions: List of question dictionaries
        chat_id: Chat ID to send quizzes to
        
    Returns:
        Tuple of (sent count, error count, list of failed question numbers)
    """
    sent_count = 0
    error_count = 0
    failed_questions = []
    
    for i, q in enumerate(questions, 1):
        try:
            # Add numbering to the question
            original_question = q['question']
            # Check if the question already starts with a number
            if not re.match(r'^\d+\.\s', original_question):
                numbered_question = f"{i}. {original_question}"
            else:
                # Replace existing number with sequential number
                numbered_question = re.sub(r'^\d+\.\s', f"{i}. ", original_question)
            
            await bot.send_poll(
                chat_id=chat_id,
                question=numbered_question,
                options=q['options'],
                type='quiz',
                correct_option_id=q['correct_option_id'],
                is_anonymous=False
            )
            sent_count += 1
            await asyncio.sleep(0.5)  # Avoid flood limits
        except Exception as e:
            logger.error(f"Error sending quiz {q.get('question_num', '?')}: {e}")
            error_count += 1
            failed_questions.append(q.get('question_num', '?'))
    
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
    """
    Generate a temporary file path for a user
    
    Args:
        user_id: User ID
        prefix: File prefix
        suffix: File suffix
        
    Returns:
        Path to temporary file
    """
    os.makedirs("temp", exist_ok=True)
    return os.path.join("temp", f"{prefix}{user_id}{suffix}")
