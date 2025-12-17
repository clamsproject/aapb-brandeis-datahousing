import sys
import hashlib
from types import ModuleType, FunctionType
from gc import get_referents


def getsize(obj):
    # Based on an answer from Aaron Hall in
    # https://stackoverflow.com/questions/449560/how-do-i-determine-the-size-of-an-object-in-python
    BLACKLIST = type, ModuleType, FunctionType
    if isinstance(obj, BLACKLIST):
        raise TypeError('getsize() does not take argument of type: '+ str(type(obj)))
    seen_ids = set()
    size = 0
    objects = [obj]
    while objects:
        need_referents = []
        for obj in objects:
            if not isinstance(obj, BLACKLIST) and id(obj) not in seen_ids:
                seen_ids.add(id(obj))
                size += sys.getsizeof(obj)
                need_referents.append(obj)
        objects = get_referents(*need_referents)
    return size


def hash_from_dictionary(parameters: dict):
    param_list = ['='.join(pair) for pair in parameters.items()]
    param_list.sort()
    param_string = ','.join(param_list)
    param_hash = hashlib.md5(param_string.encode('utf-8')).hexdigest()
    #print('...', param_string)
    #print('...', param_hash)
    return param_hash
