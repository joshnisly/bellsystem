''' SWAT - SBI Web Authoring and Templating

EXAMPLE
import swat

# Each entrypoint is passed an HttpRequest and returns an HttpResponse.
def index(request):
    return swat.HttpResponse('Hello World')

urls = (
    ('/', index),
)
application = swat.Application(urls)

# Entrypoint mapping:
Specify all entrypoints in a tuple of urls. 
Example:
    '/search/<s>/?name=<s>&maxhits=<i>'
URLs can use placeholders to pass values into entrypoints as positional args:
    '/<i>/' -> matches any integer
    '/<f>/' -> matches any floating point number
    '/<s>/' -> matches any text that comprises a single path component,
               (passed as a string)
    '/[s]/' -> matches any text potentially comprising multiple path
               components. Passed as a list of strings (on per path component.)
The same placeholders work for query strings except that [s] is not supported.
Query string parameters are passed as keyword arguments.

See demo.py for more examples.
'''

import cgi
import datetime
import HTMLParser
import inspect
try:
    import json # pylint: disable=F0401
except ImportError:
    import simplejson as json # pylint: disable=F0401
import os
import re
import StringIO
import tempfile
import traceback
import urllib
import urlparse
import unittest


if __name__ == '__main__':
    import sbi_path

import swat.file_uploads
import swat.static
import swat.status
import swat.templating

#### Requests
class HttpRequest:
    def __init__(self, environ, compiled_urls, templater):
        self.method = environ['REQUEST_METHOD'] # 'POST/GET'
        self.host = environ['SERVER_NAME']
        self.path_info = environ['PATH_INFO'] # The path component of the requested URL
        self.headers = HttpHeaders()
        self.POST = None # dict of POSTDATA (Only for POSTs)
        self.GET = _parse_qs(environ['QUERY_STRING'])
        self.environ = environ # (Advanced) Environment variables passed by WSGI

        ######### Private
        self._urls = compiled_urls
        self._templater = templater
        # (More initialization done in _HttpRequest.__init__.)

#### Responses
class HttpResponse:
    def __init__(self, body, code=200, content_type='text/html'):
        self.body = body
        self.code = code
        self.headers = HttpHeaders({
            'Content-Type': content_type
        })
# Headers other than Content-Type can be set after construction.
#    response = swat.HttpResponse(my_response_str)
#    response.headers['Content-Disposition'] = 'attachment; name=Big.xls'
# To stream the response piece-by-piece, pass a generator into the response:
#     def respond():
#         yield 'Hello '
#         yield 'world'
#     return swat.HttpResponse(respond())

def template_response(request, template_name, template_parms):
    ''' Returns an HttpResponse with the results of the template.
        template_parms should be a dictionary.
    '''
    safe_template_parms = make_unicode_safe(template_parms)
    
    return HttpResponse(get_template_text(request, template_name,
                                          safe_template_parms))

def string_template_response(request, template_text, template_parms):
    safe_template_parms = make_unicode_safe(template_parms)
    
    return HttpResponse(get_string_template_text(request, template_text,
                                                 safe_template_parms))

def make_unicode_safe(iterable):
    if isinstance(iterable, dict):
        for key, item in iterable.iteritems():
            if hasattr(item, '__iter__'):
                make_unicode_safe(item)
            elif isinstance(item, str):
                iterable[key] = item.decode('ascii', 'ignore').encode()
    
    elif isinstance(iterable, list):
        for elem in iterable:
            if hasattr(elem, '__iter__'):
                make_unicode_safe(elem)
            elif isinstance(elem, str):
                iterable[iterable.index(elem)] = elem.decode('ascii', 'ignore').encode()
        
    return iterable
            
def file_response(request, file_path, force_download=False):
    ''' Serves a file back to the browser. '''
    return swat.static.serve_file(request, file_path, force_download=force_download)

def redirect_response(request, url):
    response = HttpResponse('The item you requested is available elsewhere.',
                            code=302, content_type='text/plain')
    response.headers['Location'] = url
    return response

# get_url should be used to generate URLs instead of hardcoding them.
# This should typically be used with the redirect_response above.
def get_url(request, func, args=None, kwargs=None):
    return request.get_url(func, args, kwargs)


#### Template helper
def get_template_text(request, template_name, template_parms):
    url_prefix = request.environ['SCRIPT_NAME']
    # pylint: disable=W0212
    return request._templater.get_template_text(url_prefix, template_name,
                                                template_parms)

def get_string_template_text(request, template_text, template_parms):
    url_prefix = request.environ['SCRIPT_NAME']
    # pylint: disable=W0212
    return request._templater.get_string_template_text(url_prefix, template_text,
                                                       template_parms)

#### Long-running functions
def thread_spawn(func, args=None, kwargs=None):
    ''' Runs func in another thread, and returns a key to retrieve status. '''
    #TODO: document function parameters and status key
    return swat.status.thread_spawn(func, args, kwargs)

def thread_spawn_exclusive(func, args=None, kwargs=None):
    ''' Same as spawn_function, but only one can be run at once. '''
    return swat.status.thread_spawn_exclusive(func, args, kwargs)

def thread_append_status_text(status_key, text):
    swat.status.thread_append_status_text(status_key, text)

def thread_append_status_line(status_key, text):
    text = text.rstrip('\n') + '\n'
    swat.status.thread_append_status_text(status_key, text)

def thread_set_user_data(status_key, data):
    swat.status.thread_set_user_data(status_key, data)

def thread_modify_user_data(status_key, func):
    swat.status.thread_modify_user_data(status_key, func)

def thread_cancel(status_key):
    swat.status.thread_cancel(status_key)

def thread_get_status(status_key):
    return swat.status.thread_get_status(status_key)

def status_register_key(status_key):
    swat.status.register_status_key(status_key)

ExclusivityError = swat.status.ExclusivityError
CanceledError = swat.status.CanceledError


def status_thread(exclusive):
    def wrap(func):
        @json_request
        def wrap_inner(request, *a, **kw):
            a = (request,) + a
            if exclusive:
                status_key = swat.status.thread_spawn_exclusive(func, args=a, kwargs=kw)
            else:
                status_key = swat.status.thread_spawn(func, args=a, kwargs=kw)
            return {
                'status_key': status_key,
                'status_url': get_url(request, _thread_status_entrypoint),
                'cancel_url': get_url(request, _thread_cancel_entrypoint),
            }
        return wrap_inner

    return wrap

class CanceledUploadError(Exception):
    pass

#### JSON entrypoint decorator
# When communicating with an entrypoint via AJAX, we typically use JSON
# to transfer data. To handle this in an entrypoint, use the 'json_request'
# decorator:
#     @swat.json_request
#     def status_ajax(request):
#         status_uid = request.JSON['uid']
#         return {'status': my_status_str}
# Notice the request.JSON member. It is filled in with the deserialized
# form of the JSON POSTDATA when the json_request decorator is used.
# Additionally, the entrypoint can simply return an object, and it will be
# serialized back to JSON. If an exception occurs, it will be serialized
# in the following format:
#     {'error': str(exception), 'traceback': traceback.format_exc()}
def json_request(func):
    ''' To be used as a decorator for entrypoints dealing with JSON. '''
    def wrap(request, *a, **kw):
        try:
            if request.method == 'POST':
                if request.raw_post_data:
                    request.JSON = json.loads(request.raw_post_data.read())
                else:
                    request.JSON = {}
            response = func(request, *a, **kw)
        except Exception, e:
            if not request.should_show_tracebacks:
                return _raw_return_json({
                    'error': 'Something bad happened.'
                })
            error = str(e) or repr(e) or 'An unknown error occurred.'
            return _raw_return_json({
                'error': error,
                'traceback': traceback.format_exc()
            })

        if isinstance(response, HttpResponse):
            return response

        return _raw_return_json(response)

    return wrap

#### Running standalone
# Usage:
# if __name__ == '__main__':
#    swat.run_standalone(application)
def run_standalone(application, host_spec=None, should_reload=True, extra_environ=None):
    ''' Starts a standalone server serving on host_spec (defaults to
        localhost:8080).
    '''
    host_spec = host_spec or '127.0.0.1:8080'

    if not extra_environ is None:
        application.set_extra_environ(extra_environ)

    def main(host_spec):
        host, ignored, port = host_spec.partition(':')
        port = int(port) if port else 80
        import swat.wsgiserver
        application.enable_logging()
        server = swat.wsgiserver.CherryPyWSGIServer((host, port), application,
                                                    server_name=host)
        print 'Starting standalone server on %s:%i...' % (host, port)
        try:
            server.start()
        except KeyboardInterrupt:
            print "Stopping standalone server..."
            server.stop()
            print "Standalone server stopped."
            raise

    if should_reload:
        import swat.autoreload
        swat.autoreload.main(main, args=(host_spec,))
    else:
        main(host_spec)



############################### Implementation

class Application(object):
    def __init__(self, urls, show_tracebacks=True, send_500_emails=True,
                 client_facing_error='Something bad happened'):
        if os.path.exists(self._get_static_dir()):
            # Automatically serve static files
            # Note: we only serve static files if there's a static folder
            # in the application's directory. This allows us to turn off
            # static file serving for security-sensitive apps (like the IFX.)
            urls = urls + (
                ('/static/<i>/[s]', swat.static.serve_dir,
                    {'root': self._get_static_dir()}),
                ('/swat_static/<i>/[s]', swat.static.serve_dir,
                    {'root': self._get_swat_static_dir()})
            )

        # Automatically handle status
        urls = (('/swat_thread_status/', _thread_status_entrypoint),
                ('/swat_thread_cancel/', _thread_cancel_entrypoint),) + urls

        # Compile urls
        self._urls = [(_compile_url(x[0]), x[1], x[2] if len(x) > 2 else {})
                      for x in urls]
        self._templater = swat.templating.TemplateEngine(self._get_static_dir(),
                                                    self._get_swat_static_dir(),
                                                    self._get_template_dir(),
                                                    self._urls)
        self._should_log = False
        self._should_show_tracebacks = show_tracebacks
        self._send_500_emails = send_500_emails
        self._extra_environ = {}
        self._client_facing_error = client_facing_error

    def enable_logging(self):
        self._should_log = True

    def set_extra_environ(self, extra_environ):
        self._extra_environ = extra_environ

    def add_static_dir(self, name, path):
        self._templater.add_static_path(name, path)

    def __call__(self, environ, start_response):
        environ.update(self._extra_environ)

        # Load request headers and post data
        request = _HttpRequest(environ, self._urls, self._templater)
        request.should_show_tracebacks = self._should_show_tracebacks
        if request.method == 'POST':
            self._handle_post_data(environ, request)

        # Run handler function
        response = self._dispatch(request)
        headers = HttpHeaders(response.headers)
        if isinstance(response.body, unicode):
            response.body = response.body.encode('utf8')
            headers['Content-Type'] = headers.get('Content-Type') + \
                                      '; charset=utf-8'
        if isinstance(response.body, basestring):
            headers['Content-Length'] = str(len(response.body))
        
        # Optionally log request
        if self._should_log:
            self._log_request(request, response)

        # Send back response headers, and send response headers
        http_status_line = str(response.code) + ' ' + \
                           _HTTP_CODES[response.code]
        headers = zip(headers, headers.values())
        start_response(http_status_line, headers)

        # Send actual response
        if isinstance(response.body, basestring):
            return [response.body]
        else:
            return response.body

    def _dispatch(self, request):
        # TODO: Add this in as conditional validation
        #if request.environ['wsgi.multiprocess']:
        #    return HttpResponse('Multi-process MPM is not supported',
        #                        code=200, content_type='text/plain')
        
        full_url = '%s?%s' % (request.path_info,
                              request.environ['QUERY_STRING'])
        for url_spec, func, additional_args in self._urls:
            matched_args, matched_kwargs = _match_parms(url_spec, full_url)
            if not matched_args is None:
                try:
                    args = [request] + matched_args
                    kwargs = dict(additional_args)
                    kwargs.update(matched_kwargs)

                    res = self.impl_dispatch(func, args, kwargs)

                    if not isinstance(res, HttpResponse):
                        raise ValueError, 'Returned type was not a response.'

                    return res
                except Exception:
                    return self._report_500(request)

        # TODO: display nice 404 page
        return HttpResponse('Nothing to see here, move along.', code=404)
    
    def impl_dispatch(self, func, args, kwargs):
        """ This function is provided to allow derived classes to modify the
            request before actually invoking the handler. It also allows
            implementation-specific handling of database transactions, etc.
        """
        return func(*args, **kwargs)

    def _report_500(self, request):
        ''' Handle 500 server errors for both
            internal and external viewing.
        '''
        tb = traceback.format_exc()
        if self._send_500_emails:
            import sbi_logger # pylint: disable=F0401
            doc = 'Evaluate & Respond on SWAT 500s (Internal Server Error)'
            logger = sbi_logger.config_log(docstring_override=doc)    
            client_ip_addr = request.environ['REMOTE_ADDR']
            logger.error('\n'.join(['SWAT reported a request attempt returning with 500',
                                    'Server: %s' % request.host,
                                    'User: %s' % request.environ.get('REMOTE_USER', 'UNKNOWN'),
                                    'Client IP address: %s' % client_ip_addr,
                                    'URL: %s' % request.path_info,
                                    'Method: %s' % request.method,
                                    'Parameters: %s' % request.GET if request.GET else '',
                                    'Headers: %s' % request.headers,
                                    '\n\n%s' % tb
                                    ]))
        
        client_message = self._client_facing_error
        if self._should_show_tracebacks:
            client_message += ': \r\n%s' % tb
        
        return HttpResponse(client_message, code=500, content_type='text/plain')
        
    
    def _handle_post_data(self, environ, request):
        request.raw_post_data = None
        request.POST = {}

        if not 'CONTENT_LENGTH' in environ:
            return

        length = int(environ['CONTENT_LENGTH'])
        request.raw_post_data = _PostDataReader(environ['wsgi.input'],
                                                length)
        
        if not 'CONTENT_TYPE' in environ:
            return

        content_type, ignored_hdict = _parse_header(environ['CONTENT_TYPE'])

        if content_type.lower().startswith('multipart'):
            # The entrypoint can elect to process this later if desired.
            return
        
        # Read in post data from client
        if content_type.lower() == 'application/x-www-form-urlencoded':
            post_data = request.raw_post_data.read()
            request.POST = _parse_qs(post_data)
            parser = HTMLParser.HTMLParser()
            for field in request.POST:
                request.POST[field] = parser.unescape(request.POST[field])
            request.raw_post_data = StringIO.StringIO(post_data)
    
    def _log_request(self, request, response):
        print '%s - %s %s %i %s' % (
                datetime.datetime.now().strftime('%d/%m/%Y:%H:%M:%S'),
                request.method,
                request.path_info,
                response.code,
                response.headers.get('Content-Length', '')
            )

    def _get_template_dir(self):
        return os.path.join(self._get_calling_file_dir(), 'templates')

    def _get_static_dir(self):
        return os.path.join(self._get_calling_file_dir(), 'static')

    def _get_swat_static_dir(self):
        parent_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(parent_dir, 'swat_static')

    def _get_calling_file_dir(self):
        return os.path.dirname(self._get_calling_file())

    def _get_calling_file(self):
        # TODO: This does not work if the consumer derives from this class
        # and adds an __init__ function. It will return the file for the
        # __init__, not the actual calling file.
        stack = traceback.extract_stack()
        files = [x[0] for x in stack]
        files = filter(lambda x: x != files[-1], files)
        assert len(files)
        calling_file = files[-1]
        return calling_file





##################### Internals ########################
def reverse(func, compiled_urls, args, kwargs):
    for url in compiled_urls:
        url_func = get_wrapped_func(url[1])

        # Allow the caller to pass in a string
        if isinstance(func, basestring):
            target_func = url_func
            url_func = target_func.__name__
            if target_func.__module__ != '__main__' and \
                    not target_func.__module__.startswith('_mod_wsgi_'):
                url_func = target_func.__module__ + '.' + url_func

        if func != url_func:
            continue

        # The function matches. Make sure that the args also match.
        url = _substitute_url_args(url[0], args, kwargs)
        if not url is None:
            return url

    return ''

def get_wrapped_func(func):
    ''' Peels off decorators to get at the wrapped function. '''
    while func.func_closure:
        func = func.func_closure[-1].cell_contents
    return func

class _HttpRequest(HttpRequest):
    def __init__(self, *args, **kwargs):
        HttpRequest.__init__(self, *args, **kwargs)

        if not self.path_info:
            self.path_info = '/'

        # Init headers from environment variables.
        for key in self.environ:
            if key.startswith('HTTP_'):
                header_name = key[5:].replace('_', '-')
                self.headers[header_name] = self.environ[key]

        self.should_show_tracebacks = True

    def get_url(self, func, args=None, kwargs=None):
        url_prefix = self.environ['SCRIPT_NAME']
        rel_url = reverse(func, self._urls, args or [], kwargs or {})
        return url_prefix + rel_url

    def handle_file_uploads(self, handler):
        content_type, hdict = _parse_header(self.environ['CONTENT_TYPE'])

        if not content_type.lower().startswith('multipart'):
            return

        boundary = hdict['boundary']
        swat.file_uploads.parse_multipart(self.raw_post_data, boundary,
                                          self.POST, handler)

@json_request
def _thread_status_entrypoint(request):
    status_info = thread_get_status(request.JSON['status_key'])
    if not status_info.pop('is_randomly_generated'):
        raise ValueError('Invalid status key!')
    return status_info

@json_request
def _thread_cancel_entrypoint(request):
    return thread_cancel(request.JSON['status_key'])

##### URL matching
_URL_ARG_REGEX = re.compile('(<([ifs]{1})>|\[(s)\])')
def _parse_qs(query_string):
    ''' Wrapper for urlparse.parse_qs that *doesn't* handle multiple
        identically named paramters.
    '''
    try:
        # pylint: disable=E1101
        parms = urlparse.parse_qs(query_string, keep_blank_values=True)
    except AttributeError:
        parms = cgi.parse_qs(query_string, keep_blank_values=True)
    for name in parms:
        parms[name] = parms[name][0]
    return parms

def _compile_url(url_spec):
    path, ignored, query_string = url_spec.partition('?')

    # Path parameters
    specs = _URL_ARG_REGEX.findall(path)

    arg_types = []
    for ignored, type_spec, list_spec in specs:
        if list_spec:
            arg_types.append(list)
        elif type_spec == 'i':
            arg_types.append(int)
        elif type_spec == 'f':
            arg_types.append(float)
        elif type_spec == 's':
            arg_types.append(str)
        else:
            assert False, 'Invalid parm type: ' + type_spec

    # Query parameters
    parms = _parse_qs(query_string)
    query_args = {}
    for name in parms:
        type_spec = parms[name]
        if type_spec == '<i>':
            query_args[name] = int
        elif type_spec == '<f>':
            query_args[name] = float
        elif type_spec == '<s>':
            query_args[name] = str
        else:
            assert False, 'Invalid parm type: ' + type_spec

    return { 
        'path_spec': path,
        'regex': re.compile(_url_spec_to_regex(path)),
        'path_arg_types': arg_types,
        'query_arg_types': query_args
    }

def _quote(url_arg):
    return urllib.quote(str(url_arg))

def _unquote(url_arg):
    return urllib.unquote(url_arg)

def _get_base_type(type_):
    if type_ == long:
        return int
    if type_ == unicode:
        return str
    return type_

def _substitute_url_args(compiled_url_spec, args, kwargs):
    arg_types = compiled_url_spec['path_arg_types']
    if len(args) != len(arg_types):
        return None
    args_match = True
    for arg, arg_type in zip(args, arg_types):
        if _get_base_type(type(arg)) != _get_base_type(arg_type):
            args_match = False
            break
    if not args_match:
        return None

    # Path parameters
    parms = args[::-1]
    def replace(match):
        parm = parms.pop()
        if match.groups()[2]:
            parm = [_quote(p) for p in parm]
            return '/'.join(parm)
        return _quote(parm)

    path = _URL_ARG_REGEX.sub(replace, compiled_url_spec['path_spec'])
    if not kwargs:
        return path

    # Do not include query parms for None values.
    for key, value in kwargs.items():
        if value is None:
            del kwargs[key]

    query_str = urllib.urlencode(kwargs)
    return '%s?%s' % (path, query_str)


def _match_parms(compiled_url, url):
    """ Returns an array of matched arguments
    if the url matches, else None. """
    path, ignored, query_string = url.partition('?')

    match = compiled_url['regex'].match(path)
    if not match:
        return None, None

    # Path parameters
    args = []
    for type_, match in zip(compiled_url['path_arg_types'], match.groups()):
        if type_ == list:
            if match:
                match = match.split('/')
            else:
                match = []
            args.append([_unquote(m) for m in match])
        else:
            args.append(type_(_unquote(match)))

    # Query parameters
    query_parms = _parse_qs(query_string)
    kwargs = {}
    for name in compiled_url['query_arg_types']:
        type_ = compiled_url['query_arg_types'][name]
        if name in query_parms and query_parms[name] != '':
            try:
                kwargs[name] = type_(query_parms[name])
            except ValueError:
                return None, None
        else:
            kwargs[name] = None

    return args, kwargs

def _url_spec_to_regex(url_spec):
    result = url_spec
    result = result.replace('<i>', r'(\d+)')
    result = result.replace('<s>', r'([^/]+)') # Anything that is not a slash
    result = result.replace('[s]', r'(.*)') # Anything that is not a slash
    return '^' + result + '$'

##### Headers
class HttpHeaders(dict):
    ''' Handles case-insensitivity by title-casing keys.
        Inspired by CherryPy.
    '''
    def __getitem__(self, key):
        return dict.__getitem__(self, str(key).title())
    
    def __setitem__(self, key, value):
        dict.__setitem__(self, str(key).title(), value)
    
    def __delitem__(self, key):
        dict.__delitem__(self, str(key).title())
    
    def __contains__(self, key):
        return dict.__contains__(self, str(key).title())
    
    def get(self, key, default=None):
        return dict.get(self, str(key).title(), default)
    
    def has_key(self, key):
        return dict.has_key(self, str(key).title())
    
    def update(self, source):
        for key in source.keys():
            self.__setitem__(str(key).title(), source[key])

    def parse_header(self, key):
        """
        Parse a Content-Type like header
        
        Return the main Content-Type and a dictionary of options
        
        Based off cgi.parse_header
        """
        #Get header line
        header = self.get(key)
        
        return _parse_header(header)    


def _parse_header(header):
    """
    Parse a Content-Type like header
    
    Return the main Content-Type and a dictionary of options
    
    Based off cgi.parse_header
    """
    def _normalize_value(value):
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            value = value[1:-1].replace('\\\\', '\\').replace('\\"', '"')
        return value
    
    #Get main content_type        
    content_type, ignored_sep, option_str = header.partition(";")
    content_type = content_type.strip()
    options_str = option_str.strip()
    
    #Example:
    #header = 'content-type: type; option1=option; option2="option\";option"'
    #options_str = 'option1=option; option2="\\option\";option"'
    #parts = ['option1', 'option', 'option2', '\option";option']
    parts = re.split(r'\s*=\s*(".*?(?<!\\)"|.*?)(?:;\s*|\s*$)', options_str)
    
    assert parts.pop() == ""        #We have matched entire string
    assert len(parts) % 2 == 0      #Sanity check that each key have a value
    
    hdict = dict(zip(parts[0::2], parts[1::2]))
    
    hdict = dict((name, _normalize_value(value)) for \
                 name, value in hdict.items())
    
    return content_type, hdict

class _PostDataReader(object):
    ''' Very simple reading wrapper to avoid blocking. '''
    def __init__(self, post_file_obj, length):
        self._file = post_file_obj
        self._remaining_size = length
        
    def read(self, length=None):
        if length is None:
            length = self._remaining_size
            
        length = min(length, self._remaining_size)
        data = self._file.read(length)
        self._remaining_size -= len(data)
        return data
    
    def is_at_end(self):
        return self._remaining_size == 0
   
##### JSON
def _raw_return_json(obj):
    return HttpResponse(json.dumps(obj), content_type='text/javascript')

_HTTP_CODES = {
    200: 'OK',
    206: 'Partial Content',
    302: 'Moved Permanently',
    404: 'File not found',
    416: 'Requested range not satisfiable',
    500: 'Internal server error',
    503: 'Service Unavailable',
}

##### Tests

class ReverseTest(unittest.TestCase):
    def _test(self, url_spec, args, kwargs, expected):
        compiled = _compile_url(url_spec)
        encountered = _substitute_url_args(compiled, args, kwargs)
        self.assertEquals(encountered, expected)

    def test_no_args(self):
        self._test('/', [], {}, '/')

    def test_wrong_number_of_args(self):
        self._test('/', [1], {}, None)
        self._test('/<i>/', [], {}, None)

    def test_single_arg(self):
        self._test('/<i>/', [1], {}, '/1/')
        self._test('/<i>/', ['s'], {}, None)
        self._test('/<s>/', ['s'], {}, '/s/')

    def test_multiple_args(self):
        self._test('/<i>/<i>/', [1, 2], {}, '/1/2/')
        self._test('/<i>/<s>/', [1, 'fdsa'], {}, '/1/fdsa/')
        self._test('/[s]/', [['fdsa', 'fdsa']], {}, '/fdsa/fdsa/')
        # TODO: better testing of <s> with args with slashes

    def test_query_parms(self):
        self._test('/?parm=<i>', [], {'parm': 42}, '/?parm=42')
        self._test('/<i>/?parm=<s>', [53], {'parm': 'fdsa'}, '/53/?parm=fdsa')

class MatchesUrlTest(unittest.TestCase):
    def _test(self, url_spec, url, expected_args, expected_kwargs=None):
        expected_kwargs = expected_kwargs or {}
        if expected_args is None:
            expected_kwargs = None
        compiled = _compile_url(url_spec)
        encountered_args, encountered_kwargs = _match_parms(compiled, url)
        self.assertEquals(encountered_args, expected_args)
        self.assertEquals(encountered_kwargs, expected_kwargs)

    def test_basic(self):
        self._test('/', '/', [])
        self._test('/test/', '/test/', [])
        self._test('/', '/nomatch', None)
        self._test('/nomatch/', '/', None)


    def test_int(self):
        self._test('/<i>/', '/42/', [42])
        self._test('/test/<i>/test/', '/test/42/test/', [42])
        self._test('/<i>/<i>/', '/42/53/', [42, 53])

    def test_str(self):
        self._test('/<s>/', '/fdsa/', ['fdsa'])
        # Don't match multiple path components
        self._test('/<s>/', '/fdsa/fdsa/', None)
        self._test('/[s]/', '/fdsa/fdsa/', [['fdsa', 'fdsa']])

    def test_query_parms(self):
        self._test('/?parm=<i>', '/', [], {'parm': None})
        self._test('/?parm=<i>', '/?parm=42', [], {'parm': 42})
        self._test('/?parm=<s>', '/?parm=42', [], {'parm': '42'})
        self._test('/?parm=<i>', '/?parm=fdsa', None)

        self._test('/<i>/?parm=<s>', '/53/?parm=42', [53], {'parm': '42'})
        self._test('/<i>/?parm=<s>&size=<i>', '/53/?parm=42&size=64', [53],
                   {'parm': '42', 'size': 64})
    
    def test_encode(self):
        self._test('/<s>/', '/this%2Fis%2Fencoded/', ['this/is/encoded'])
        self._test('/[s]/', '/this%2Fis/a%2Ftest/', [['this/is', 'a/test']])

class UrlToRegexTest(unittest.TestCase):
    def _test(self, url_spec, expected):
        encountered = _url_spec_to_regex(url_spec)
        self.assertEquals(encountered, expected)

    def test_basic(self):
        self._test('/', '^/$')
        self._test('/bogus/', '^/bogus/$')
        self._test('/bogus', '^/bogus$')

    def test_int(self):
        self._test('/<i>/', r'^/(\d+)/$')
        self._test('/test/<i>/test/', r'^/test/(\d+)/test/$')
        self._test('/<i>/<i>/', r'^/(\d+)/(\d+)/$')

    def test_str(self):
        self._test('/<s>/', r'^/([^/]+)/$')
        self._test('/[s]/', r'^/(.*)/$')

if __name__ == '__main__':
    # Run tests
    unittest.main()
