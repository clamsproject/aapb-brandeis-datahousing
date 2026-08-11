
class StorageServerError(Exception):
    pass


class StorageWarning(Warning):
    pass


class UploadWarning(StorageWarning):

    def __init__(self, message: str, path: str = None):
        self.msg = f'UploadWarning: {message}'
        self.path = path

    def __str__(self):
        return self.msg


class EmptyMmifWarning(StorageWarning):

    def __init__(self, path: str = None):
        self.msg = 'EmptyMmifWarning: not saving the MMIF file because it has no views'
        self.path = path

    def __str__(self):
        return self.msg
