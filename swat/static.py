
import mimetools
import mimetypes
mimetypes.init()
import os
import unittest
if os.name == 'nt':
    # For DeletableFile below
    import win32con # pylint: disable=F0401
    import win32file # pylint: disable=F0401


import swat

CHUNK_SIZE=64*1024

# Add standard types missing from mimetypes.
mimetypes.add_type('image/png', '.png')

def serve_dir(request, ignored_version, path_parts, root):
    # TODO: eventually we could respect the version here.
    root = os.path.normpath(os.path.abspath(root))
    full_path = os.path.normpath(os.path.join(root, *path_parts))
    assert full_path.startswith(root + os.sep)
    response = serve_file(request, full_path)
    max_age = 30 * 24 * 60 * 60
    response.headers['Cache-Control'] = 'max-age=%i; must-revalidate' % max_age
    return response


def serve_file(request, path, force_download=False):
    content_type = mimetypes.guess_type(path)[0] or ''
    try:
        size = os.stat(path).st_size
    except OSError:
        return swat.HttpResponse('File not found', code=404, 
                                 content_type='text/plain')
    if 'Range' in request.headers:
        parts = _determine_ranges(request.headers['Range'], size)
        if parts is None:
            return swat.HttpResponse('Invalid byte ranges', code=416)

        if len(parts) == 1:
            part = parts[0]
            length = part['end'] - part['start'] + 1 # End is inclusive
            serve = _serve_file_part(path, part['start'], part['end'])
            response = swat.HttpResponse(serve, code=206)
            response.headers['Content-Length'] = str(length)
            response.headers['Content-Range'] = part['spec']
            return response
        else:
            boundary = mimetools.choose_boundary()
            def serve(path, parts, boundary):
                for part in parts:
                    yield '\r\n--%s\r\n' % boundary
                    yield 'Content-Type: %s\r\n' % content_type
                    yield 'Content-Range: bytes %s\r\n\r\n' % part['spec']
                    for chunk in _serve_file_part(path, part['start'],
                                                  part['end']):
                        yield chunk
                yield '\r\n--%s--\r\n' % boundary
            response = swat.HttpResponse(serve(path, parts, boundary), code=206)
            response.headers['Content-Type'] = \
                    'multipart/byteranges; boundary=%s' % boundary
            response.headers['Accept-Ranges'] = 'bytes'
            return response

    def serve_entire():
        file_ = DeletableFile(path)
        while True:
            chunk = file_.read(CHUNK_SIZE)
            if not chunk:
                break
            yield chunk
        file_.close()
    response = swat.HttpResponse(serve_entire(), content_type=content_type)
    
    # Only set the content-length if the size is less then 2GB because of a mod wsgi bug.
    if size < 2*1024**3:
        response.headers['Content-Length'] = str(size)

    if force_download:
        content_disposition = 'attachment; filename="%s"' % \
                            os.path.basename(path)
        response.headers['Content-Disposition'] = content_disposition
    
    return response



def _determine_ranges(ranges_str, total_size):
    assert ranges_str.startswith('bytes=')
    ranges_str = ranges_str[6:]
    ranges = ranges_str.split(',')
    result_ranges = []
    for spec in ranges:
        first, sep, last = spec.partition('-')
        # Format: "-x"
        if not first:
            first = total_size - int(last)
            last = total_size - 1

        elif not last:
            if sep:
                # Format: "x-"
                first = int(first)
                last = total_size - 1
            else:
                # Format: "x"
                first = int(first)
                last = first
        else:
            # Format: "x-y"
            first = int(first)
            last = int(last)

        first = min(first, total_size - 1)
        last = min(last, total_size - 1)
        result_ranges.append({
            'start': first,
            'end': last,
            'spec': '%i-%i/%i' % (first, last, total_size)
        })
    return result_ranges

def _serve_file_part(path, start, end):
    file_ = DeletableFile(path)
    file_.seek(start)
    remaining = end - start + 1 # End is inclusive
    while True:
        if remaining == 0:
            break
        chunk = file_.read(min(remaining, CHUNK_SIZE))
        if not chunk:
            break
        yield chunk
        remaining -= len(chunk)
    file_.close()


class DeletableFile(object):
    ''' DeletableFile acts like a normal file, but allows the
        file to be deleted while open.
    '''

    def __init__(self, path):
        self._path = path
        self._file = None
        if os.name == 'nt':
            self._file = win32file.CreateFile(path,
                          win32file.GENERIC_READ,
                          win32file.FILE_SHARE_READ|\
                                  win32file.FILE_SHARE_DELETE|\
                                  win32file.FILE_SHARE_WRITE,
                          None,
                          win32file.OPEN_EXISTING,
                          0,
                          None)
        else:
            self._file = open(path, 'rb')

    def read(self, amount=64*1024):
        if os.name == 'nt':
            result, buf = win32file.ReadFile(self._file, amount)
            if result:
                raise IOError, 'Unable to read file: %i' % result
            return buf
        else:
            return self._file.read(amount)

    def seek(self, pos_from_start):
        if os.name == 'nt':
            win32file.SetFilePointer(self._file, pos_from_start,
                                     win32con.FILE_BEGIN)
        else:
            self._file.seek(pos_from_start)



    def close(self):
        if os.name == 'nt':
            win32file.CloseHandle(self._file)
        else:
            return self._file.close()

    def __del__(self):
        self.close()


class RangesTest(unittest.TestCase):
    # pylint: disable=R0913
    def _test(self, header, total_size, start, end, spec):
        encountered = _determine_ranges(header, total_size)
        assert len(encountered) == 1
        encountered = encountered[0]
        self.assertEquals(encountered['start'], start)
        self.assertEquals(encountered['end'], end)
        self.assertEquals(encountered['spec'], spec)

    def test_simple(self):
        self._test('bytes=0-499', 1000, 0, 499, '0-499/1000')

        self._test('bytes=0-', 1000, 0, 999, '0-999/1000')
        self._test('bytes=0', 1000, 0, 0, '0-0/1000')
        self._test('bytes=-1', 1000, 999, 999, '999-999/1000')
        self._test('bytes=-50', 1000, 950, 999, '950-999/1000')

        # Limit to actual file size.
        self._test('bytes=0-499', 400, 0, 399, '0-399/400')

if __name__ == '__main__':
    unittest.main()
