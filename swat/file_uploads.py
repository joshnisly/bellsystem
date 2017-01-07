import os
import tempfile
import unittest

import swat

def parse_multipart(post_file, boundary, post_data, handler):
    file_handles = {} # filename to handle
    for filename, name, chunk in _yield_chunks(post_file, boundary):
        if filename is None:
            if not name is None:
                if not name in post_data:
                    post_data[name] = ''
                post_data[name] += chunk
        else:
            # Hack to remove slashes to avoid problems with os.path.join.
            filename = os.path.basename(filename)
        
            if not filename in file_handles:
                if hasattr(handler, 'on_file_start_2'):
                    file_handles[filename] = handler.on_file_start_2(name, filename)
                else:
                    file_handles[filename] = handler.on_file_start(filename)
        
            file_handles[filename].write(chunk)

            try:
                handler.on_file_progress(filename, chunk)
            except (swat.CanceledUploadError, Exception):
                for handle in file_handles.values():
                    handle.close()
                # It's a little weird to pretend the upload was
                # cancelled if on_file_progress threw an exception, but
                # it allows the caller to clean up.
                handler.on_upload_canceled()
                raise

    for handle in file_handles.values():
        handle.close()

    handler.on_upload_complete()

class DefaultUploader(object):
    def __init__(self):
        self.FILES = {}

    def on_file_start(self, filename):
        handle, path = tempfile.mkstemp(prefix="upload - %s - " % filename)
        self.FILES[filename] = path
        return os.fdopen(handle)

    def on_file_progress(self, filename, data):
        pass

    def on_upload_canceled(self):
        pass

    def on_upload_complete(self):
        pass


def _yield_chunks(input_file, boundary, chunk_size=10 * 1024):
    ''' Yields ('filename', 'data') '''
    mid_boundary = '\r\n--' + boundary + '\r\n'
    end_boundary = '\r\n--' + boundary + '--'
    
    reader = _BoundaryReader(input_file, chunk_size)
    #Read prologue
    reader.read_until_boundary(['--' + boundary], True)
    while True:
        headers_str = reader.read_until_boundary(['\r\n\r\n'], True)
        section_headers = _parse_headers(headers_str)
        content_disposition = section_headers.parse_header('content-disposition')[1]
        filename = content_disposition.get('filename', None)
        name = content_disposition.get('name', None)

        while True:
            section_part = reader.read_until_boundary([mid_boundary, end_boundary], False)
            if section_part is None:
                return
            
            yield filename, name, section_part
            if not reader.get_last_boundary() is None:
                if reader.get_last_boundary() == end_boundary:
                    return
                break



class _BoundaryReader(object):
    def __init__(self, input_file, chunk_size):
        self._chunk_size = chunk_size
        self._input = _PostFileWrapper(input_file)
        self._last_boundary = None
    
    def read_until_boundary(self, boundaries, read_until_found):
        data = self._read(boundaries)
        if read_until_found:
            while self.get_last_boundary() is None:
                this_data = self._read(boundaries)
                if not len(this_data):
                    raise ValueError, 'Invalid post data.'
                data += this_data
        return data
    
    def get_last_boundary(self):
        return self._last_boundary

    def _read(self, boundaries):
        self._last_boundary = None

        # Get data (grabbed more than chunk size to check for boundary off end)
        max_boundary_len = max(len(x) for x in boundaries)
        amount_to_read = self._chunk_size + max_boundary_len
        data = self._input.read(amount_to_read)
        
        # Stop at boundary start (if there is one).
        for boundary in boundaries:
            pos = data.find(boundary)
            if pos != -1:
                # Return the entire chunk.
                if pos > self._chunk_size:
                    break
                
                # Seek back to end of boundary (start of next chunk).
                boundary_end = pos + len(boundary)
                self._input.seek_back(len(data) - boundary_end)
                
                # Record which boundary we found.
                self._last_boundary = boundary
                
                # Return up to boundary start.
                return data[:pos]
        
        # Return the entire chunk.
        self._input.seek_back(max_boundary_len)
        return data[:-max_boundary_len]


class _PostFileWrapper():
    def __init__(self, post_file):
        self._file = post_file
        self._last_read = ''
        self._last_read_cursor = 0

    def read(self, chunk_size):
        cache_data = self._last_read[self._last_read_cursor:]

        amount_to_read = chunk_size - len(cache_data)

        if not self._file.is_at_end():
            new_data = self._file.read(amount_to_read)
        else:
            new_data = ''
            
        self._last_read = cache_data + new_data

        self._last_read_cursor = len(self._last_read)
        return self._last_read
    
    def seek_back(self, back_count):
        self._last_read_cursor = self._last_read_cursor - back_count
        assert self._last_read_cursor > 0


def _parse_headers(headers_str):
    headers = {}
    header_lines = headers_str.split('\r\n')
    for line in header_lines:
        key, ignored_sep, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        
        headers[key.title()] = value
    return swat.HttpHeaders(headers)


class UploadTesting(unittest.TestCase):
    def test1(self):
        text_input = '''\
--bogus\r\n\
Content-Disposition: form-data; name="File"; filename="Makefile"\r\n\
Content-Type: text/plain; filename="bogus"\r\n\r\n\
my cool text here\r\n\
--bogus--'''
        
        self._test(text_input, [
            ('Makefile', 'File', 'my co'),
            ('Makefile', 'File', 'ol te'),
            ('Makefile', 'File', 'xt he'),
            ('Makefile', 'File', 're'),
        ])
    
    def test2(self):
        text_input = '''\
--bogus\r\n\
Content-Disposition: form-data; name="File"; filename="Makefile"\r\n\
Content-Type: application/octet-stream\r\n\
\r\n\
test: python setup.py test\r\n\
--bogus\r\n\
Content-Disposition: form-data; name="File"; filename="Makefile"\r\n\
Content-Type: application/octet-stream\r\n\
\r\n\
release: python scripts/make-release.py\r\n\
--bogus--\r\n\
'''
        import StringIO
        class UploadHandler():
            def __init__(self):
                self.data = {}
            
            def on_file_start(self, filename):
                self.data[filename] = ''
                return StringIO.StringIO()

            def on_file_progress(self, filename, data):
                self.data[filename] += data
            
            def on_upload_complete(self):
                pass

        handler = UploadHandler()
        # pylint: disable=W0212
        post_file = swat._PostDataReader(StringIO.StringIO(text_input), len(text_input))
        swat.file_uploads.parse_multipart(post_file, 'bogus', {}, handler)
        
        self.assertEquals(handler.data.keys(), ['Makefile'])
        self.assertEquals(handler.data['Makefile'],
                          'test: python setup.py testrelease: python scripts/make-release.py')
        

    def _test(self, text_input, expected_parts):
        import StringIO
        chunks = []
        # pylint: disable=W0212
        post_file = swat._PostDataReader(StringIO.StringIO(text_input), len(text_input))
        for chunk in swat.file_uploads._yield_chunks(post_file, 'bogus', 5):
            chunks.append(chunk)
            
        self.assertEquals(chunks, expected_parts)

if __name__ == '__main__':
    unittest.main()
