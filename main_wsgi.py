#!/usr/bin/python

import swat
import sys

import bells

BELLS_FILE = sys.argv[1]


def index(request):
    if request.method == 'POST':
        if request.POST.get('Action') == 'SaveRaw':
            raw_def = request.POST['RawData']
            with open(BELLS_FILE, 'w') as output:
                output.write(raw_def)
    bells_obj = _get_bells()
    return swat.template_response(request, 'index.html', {
        'bells': bells_obj
    })


def _get_bells():
    bell_obj = bells.Bells()
    bell_obj.load_from_file(BELLS_FILE)
    return bell_obj


URLS = (
    ('/', index),
)

application = swat.Application(URLS, send_500_emails=False)

if __name__ == '__main__':
    swat.run_standalone(application, '0.0.0.0:80')
