class ApiError(Exception):
    def __init__(self, status: int, name: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.name = name
        self.message = message
