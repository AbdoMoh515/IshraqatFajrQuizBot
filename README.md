# Ishraqatfajr Quiz Bot

**Version: 1.2**

A Telegram bot that processes quiz questions from PDF or text files and handles forwarded Telegram quizzes.

## Features

- **File Processing**: Extract questions from PDF and text files and convert them to Telegram quizzes
- **Flexible Question Recognition**: Handles various question formats with different numbering and option styles
- **Quiz Forwarding**: Extract and collect forwarded Telegram quizzes and convert them to text format
- **Keyboard Controls**: Easy-to-use keyboard buttons for all operations
- **Error Handling**: Robust error handling with detailed logs

## Documentation

For a detailed explanation of the project structure, key components, and functions, please see the [Code Documentation](CODE_DOCUMENTATION.md).

## Setup Instructions

### Prerequisites

- Python 3.8 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/Ishraqatfajr-Quiz-Bot.git
   cd Ishraqatfajr-Quiz-Bot
   ```

2. Create a virtual environment (optional but recommended):
   ```
   python -m venv env
   source env/bin/activate  # On Windows: env\Scripts\activate
   ```

3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root directory with the following content:
   ```
   # Telegram Bot Configuration
   TELEGRAM_TOKEN=your_telegram_bot_token
   LOG_CHANNEL_ID=your_log_channel_id
   
   # Bot Settings
   MIN_INTERVAL_BETWEEN_FILES=60
   ```

### Running the Bot

```
python main.py
```

## Usage

### Creating Quizzes from Files

1. Click "📝 Create Quiz" button
2. Send a PDF or text file with questions in the format:
   ```
   1. Question text
   a) Option A
   b) Option B
   c) Option C
   d) Option D
   Answer: b
   ```
3. The bot will extract and send questions as Telegram quizzes
4. Use the "Show Extracted Questions" button to see all extracted questions in text format

### Extracting Forwarded Quizzes

1. Click "📥 Extract Quizzes from Forwards" button
2. Forward Telegram quizzes to the bot
3. Click "Finish Extraction" when done
4. The bot will send all questions in a single formatted text message with correct answers marked

## Question Format

The bot supports various question formats:

- Questions with or without numbers
- Options labeled with letters (a-z) followed by ")" or "."
- Answer line starting with "Answer:" or "*Answer:"
- Any number of options (minimum 2)

## Version History

- **v1.2** (Current): Added GitHub readiness, improved answer extraction, and fixed various bugs
- **v1.1**: Added flexible question recognition and keyboard controls
- **v1.0**: Initial release with basic PDF processing and quiz generation

## License

This bot is licensed under the **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)** License.

- You can use, modify, and share it **for free** as long as you give credit and do not use it commercially.
- **Commercial use is not allowed** without written permission.
- If you make changes and share them, you must keep the same license.

Read the full license terms in the [LICENSE](LICENSE) file.


## Acknowledgements

- [aiogram](https://github.com/aiogram/aiogram) - Telegram Bot framework
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) - PDF processing library
