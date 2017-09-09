#!/usr/bin/env python3

import flask
import sys

import bells

app = flask.Flask(__name__)

BELLS_FILE = sys.argv[1]


@app.route('/', methods=['GET', 'POST'])
def index():
    if flask.request.method == 'POST':
        if flask.request.form.get('Action') == 'SaveRaw':
            raw_def = flask.request.form['RawData']
            with open(BELLS_FILE, 'w') as output:
                output.write(raw_def)
    bells_obj = _get_bells()
    return flask.render_template('index.html', **{
        'bells': bells_obj
    })


def _get_bells():
    bell_obj = bells.Bells()
    bell_obj.load_from_file(BELLS_FILE)
    return bell_obj


if __name__ == '__main__':
    app.run(debug=True)
