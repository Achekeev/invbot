class BotException(Exception):
    """
    Base class for bot exceptions
    """

class BotError(BotException):
    def __init__(self, message: str, show_alert: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.show_alert = show_alert

    def __str__(self) -> str:
        return self.message