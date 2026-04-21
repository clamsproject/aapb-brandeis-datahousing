
class StorageServerError(Exception):
    
    pass


class UploadWarning(Warning):

    def __init__(self, message: str, path: str = None):
        self.msg = message
        self.path = path

    def __str__(self):
        return self.msg
