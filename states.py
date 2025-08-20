# User states
user_states = {}

# Define state constants
class States:
    IDLE = "idle"
    WAITING_FOR_FILE = "waiting_for_file"
    EXTRACTING_QUIZZES = "extracting_quizzes"
    COLLECTING_FORWARDED_QUIZZES = "collecting_forwarded_quizzes"
    ADMIN_PANEL = "admin_panel"
