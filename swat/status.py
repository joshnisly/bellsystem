
import copy
import random
import string
import sys
import threading
import traceback

class ExclusivityError(Exception):
    pass

class CanceledError(Exception):
    pass

def register_status_key(status_key):
    _status_lock.acquire()
    try:
        _register_status_key(status_key, is_randomly_generated=False)
    finally:
        _status_lock.release()

def thread_spawn(func, args=None, kwargs=None):
    status_key = _get_new_status_key()
    process_thread = _ProcessThread(status_key, func, args,
                                    kwargs, exclusive=False)
    process_thread.start()
    return status_key

def thread_spawn_exclusive(func, args=None, kwargs=None):
    func_name = _calc_func_name(func)
    _process_lock.acquire()
    # Validate that this process isn't already running
    if func_name in _process_storage:
        _process_lock.release()
        raise ExclusivityError('This process is already running.')
    status_key = _get_new_status_key()
    process_thread = _ProcessThread(status_key, func, args, kwargs, exclusive=True)

    # Register this process and release the lock before starting the thread.
    _process_storage[func_name] = process_thread
    _process_lock.release()

    process_thread.start()
    return status_key

def thread_append_status_text(status_key, text):
    assert isinstance(status_key, basestring)

    if thread_get_status(status_key)['state'] == 'canceled':
        raise CanceledError, 'User canceled.'

    def modify(status):
        status['status_str'] += text
    _thread_modify_status(status_key, modify)

def thread_set_user_data(status_key, data):
    def modify(status):
        status['user_data'] = copy.deepcopy(data)
    _thread_modify_status(status_key, modify)

def thread_modify_user_data(status_key, func):
    def modify(status):
        func(status['user_data'])
    _thread_modify_status(status_key, modify)

def thread_cancel(status_key):
    def modify(status):
        if status['state'] == 'running':
            status['state'] = 'canceled'
    _thread_modify_status(status_key, modify)

def thread_get_status(status_key):
    _status_lock.acquire()
    if not status_key in _status_storage:
        _status_lock.release()
        raise ValueError('Invalid status key.')
    status = copy.deepcopy(_status_storage[status_key])
    _status_lock.release()
    return status



####### Internals #########
def _thread_modify_status(status_key, modify_func):
    _status_lock.acquire()
    if not status_key in _status_storage:
        _status_lock.release()
        raise ValueError('Invalid status key.')
    try:
        modify_func(_status_storage[status_key])
    finally:
        _status_lock.release()

def _get_new_status_key():
    _status_lock.acquire()
    while True:
        test_key = ''.join(random.choice(string.ascii_uppercase +\
                                         string.digits)
                           for x in range(15))
        if not test_key in _status_storage:
            break
    _register_status_key(test_key)
    
    _status_lock.release()

    return test_key

def _register_status_key(status_key, is_randomly_generated=True):
    if not _status_lock.locked():
        raise ExclusivityError, "The caller must first acquire the _status_lock."
    
    if status_key in _status_storage:
        msg = 'Could not register! Status key "%s" already exists!' % status_key
        raise ExclusivityError, msg

    _status_storage[status_key] = {
        'status_str': '',
        'user_data': {},
        'state': 'running',
        'is_randomly_generated': is_randomly_generated
    }

    return status_key

def _calc_func_name(func):
    import swat
    func = swat.get_wrapped_func(func)
    return func.__module__ + '.' + func.__name__


def _thread_set_state(status_key, state):
    assert isinstance(state, basestring)

    def modify(status):
        status['state'] = state
    _thread_modify_status(status_key, modify)

def _thread_handle_error(status_key, exc_info):
    error = '\n%s: %s' % (exc_info[0].__name__, exc_info[1])
    tb = traceback.format_exception(*exc_info)

    def modify(status):
        status['status_str'] += error
        status['traceback'] = tb
        status['state'] = 'error'
    _thread_modify_status(status_key, modify)

def _remove_process_lock(func, process_thread):
    func_name = _calc_func_name(func)
    _process_lock.acquire()
    try:
        assert func_name in _process_storage
        assert _process_storage[func_name] is process_thread
        del _process_storage[func_name]
    except Exception:
        _process_lock.release()
        raise

    _process_lock.release()

class _ProcessThread(threading.Thread):
    def __init__(self, status_key, func, args, kwargs, exclusive):
        self._status_key = status_key
        self._func = func
        self._args = args or []
        self._kwargs = kwargs or {}
        self._exclusive = exclusive
        threading.Thread.__init__(self)

    def run(self):
        try:
            self._func(self._status_key, *self._args, **self._kwargs)
            _thread_set_state(self._status_key, 'finished')
        except CanceledError:
            def modify(status):
                status['status_str'] += '\nUser canceled.'
            _thread_modify_status(self._status_key, modify)
        except Exception:
            _thread_handle_error(self._status_key, sys.exc_info())
        finally:
            if self._exclusive:
                _remove_process_lock(self._func, self)

_status_storage = {}
_status_lock = threading.Lock()

_process_storage = {}
_process_lock = threading.Lock()

