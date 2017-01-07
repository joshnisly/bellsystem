#!/usr/bin/python

import time

import sbi_path

import swat

def index(request):
    if request.method == 'POST':
        print request.raw_post_data.read() # Raw post data for debugging.
        return swat.HttpResponse(repr(request.POST))

    return swat.template_response(request, 'index.html', {
                                    'title': 'swat demo'
                                  })

# Demonstrates get_url()
def cul_de_sac(request, id_):
    assert id_ > 0
    return swat.redirect_response(request,
                                  swat.get_url(request, dest, args=[id_],
                                  kwargs={'size': 10}))

# This entrypoint was redirected to by cul_de_sac
def dest(request, id_, size, name):
    return swat.HttpResponse('The number is %i and the size is %i (%s).' % \
                                (id_, size, name or ''))


# Demonstrates status framework
@swat.status_thread(exclusive=True)
def long_process(status_key, request):
    should_fail = request.JSON.get('should_fail', False)
    swat.thread_append_status_text(status_key, 'Counting to 10: \n')    
    
    if should_fail:
        for i in range(0, 3):
            swat.thread_append_status_text(status_key, '%i\n' % i)
            time.sleep(1)
        raise ValueError, 'Go away!!1'

    for i in range(0, 10):
        swat.thread_append_status_text(status_key, '%i\n' % i)
        time.sleep(1)

    swat.thread_append_status_text(status_key, 'Finished!\n')

# Multiple path components
def bogus(request, ignored_path_components):
    return swat.HttpResponse('???')


urls = (
    ('/', index),
    ('/nowhere/<i>/', cul_de_sac),
    ('/dest/<i>/?size=<i>&name=<s>', dest),
    ('/start/', long_process),
    ('/get_file/[s]/', bogus),
)
application = swat.Application(urls)

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        swat.run_standalone(application, sys.argv[1])
    else:
        swat.run_standalone(application)


