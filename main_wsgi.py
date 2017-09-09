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


@app.route('/update', methods=['GET', 'POST'])
def update():
    update_def = ['bell_num', 'hour', 'minute', 'second', 'dur']
    for key in update_def:
        assert key in flask.request.form, key

    num_elements = len(flask.request.form.getlist('bell_num'))
    for key in update_def:
        assert len(flask.request.form.getlist(key)) == num_elements, key

    activations = []
    for i in range(0, num_elements):
        activation = {}
        for key in update_def:
            activation[key] = int(flask.request.form.getlist(key)[i])

        dows = []
        for day_num in range(1, 8):
            key = 'dow_%i_%i' % (i+1, day_num)
            if key in flask.request.form:
                dows.append(day_num)
        activation['dows'] = dows
        activations.append(activation)

    bells_obj = _get_bells()
    bells_obj.set_activations(activations)
    bells_obj.save_to_file(BELLS_FILE)
    return flask.redirect(flask.url_for('index'))


def _get_bells():
    bell_obj = bells.Bells()
    bell_obj.load_from_file(BELLS_FILE)
    return bell_obj


if __name__ == '__main__':
    app.run(debug=True)
