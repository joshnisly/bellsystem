
import datetime
import unittest


class Bells(object):
    def __init__(self):
        self._bells = {}
        self._activations = []
        self._warnings = []

    def load_from_file(self, path):
        self._load_from_string(open(path).read())

    def load_from_string(self, s):
        self._load_from_string(s)

    def get_data(self):
        return {
            'bells': self._bells,
            'activations': self._activations
        }

    def get_data_as_def(self):
        def format_activation(a):
            return '%02i,%02i,%02i,%i,%i%s' % (a['hour'], a['minute'], a['second'], a['bell_num'], a['dur'],
                                         (',' + '|'.join([str(d) for d in a['dows']])) if 'dows' in a else '')

        lines = []
        for bell_num in self._bells:
            lines.append('# Bell %i %s' % (bell_num, self._bells[bell_num]))
            lines.extend([format_activation(x) for x in self._activations if x['bell_num'] == bell_num])

        lines.extend([format_activation(x) for x in self._activations if x['bell_num'] not in self._bells])
        return '\n'.join(lines)

    def get_warnings(self):
        return self._warnings

    # Returns bell #'s that should be ringing
    def get_active_bells(self, time_override=None):
        time = time_override or datetime.datetime.now()
        dow = self._get_adjusted_dow(time)

        # Filter out bells based on DOW
        activations = filter(lambda x: 'dows' not in x or dow in x['dows'], self._activations)
        activations = filter(lambda x: self._is_in_range(time, x), activations)
        return list(set([x['bell_num'] for x in activations]))

    def _load_from_string(self, s):
        for line in s.splitlines():
            line = line.strip()
            try:
                if line.startswith('#'):
                    line = line[1:].strip()
                    if line.lower().startswith('bell') and line[5].isdigit():
                        self._bells[int(line[5])] = line[6:].strip()

                else:
                    parts = line.split(',')
                    if len(parts) >= 5:
                        activation_def = dict(zip(['hour', 'minute', 'second', 'bell_num', 'dur'],
                                                  [int(x, 10) for x in parts[:5]]))
                        if len(parts) > 5:
                            activation_def['dows'] = [int(x, 10) for x in parts[5].split('|')]
                        self._activations.append(activation_def)
            except Exception:
                self._warnings.append('Unable to parse line: ' + line)

    @staticmethod
    def _get_adjusted_dow(date):
        weekday = date.isoweekday()+1
        if weekday == 8:
            return 1
        return weekday

    @staticmethod
    def _is_in_range(time, activation):
        cur_time = time.hour * 3600 + time.minute * 60 + time.second
        act_time = activation['hour'] * 3600 + activation['minute'] * 60 + activation['second']
        return act_time <= cur_time < act_time + activation['dur']


class BellsTest(unittest.TestCase):
    def setUp(self):
        self._bells = Bells()

    def testBellNames(self):
        self._bells.load_from_string('# Bell 1 (Pin 3) 1st & 2nd Grades')
        self.assertEquals(self._bells._bells, {1: '(Pin 3) 1st & 2nd Grades'})

    def testActivations(self):
        self._bells.load_from_string('''
#08,30,00,1,1
09,30,10,1,5,2|3|4|5
10,15,00,1,6
''')
        self.assertEquals(len(self._bells._activations), 2)
        self.assertEquals(self._bells._activations[0], {
            'hour': 9,
            'minute': 30,
            'second': 10,
            'bell_num': 1,
            'dur': 5,
            'dows': [2, 3, 4, 5]
        })
        self.assertEquals(self._bells._activations[1], {
            'hour': 10,
            'minute': 15,
            'second': 0,
            'bell_num': 1,
            'dur': 6
        })

    def testBadData(self):
        self._bells.load_from_string('''
a,30,10,1,5,2|3|4|5
10,30,10,1,5,2|3|4|a
''')

    def testGetActiveBells(self):
        self._bells.load_from_string('''
09,30,10,1,5,2|3|4|5
''')
        def test(date, should_activate):
            self.assertEquals(self._bells.get_active_bells(date), [1] if should_activate else [])

        # Normal activation
        test(datetime.datetime(2017, 1, 2, 9, 30, 9), False)
        test(datetime.datetime(2017, 1, 2, 9, 30, 10), True)
        test(datetime.datetime(2017, 1, 2, 9, 30, 11), True)
        test(datetime.datetime(2017, 1, 2, 9, 30, 12), True)
        test(datetime.datetime(2017, 1, 2, 9, 30, 13), True)
        test(datetime.datetime(2017, 1, 2, 9, 30, 14), True)
        test(datetime.datetime(2017, 1, 2, 9, 30, 15), False)

        # DOW filter
        test(datetime.datetime(2017, 1, 1, 9, 30, 10), False)

    def testGetDataAsDef(self):
        defs = ['''# Bell 1 My def here
09,30,10,1,5,2|3|4|5
10,15,00,1,6''']
        for def_ in defs:
            bells = Bells()
            bells.load_from_string(def_)
            self.assertEquals(bells.get_data_as_def(), def_)


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 2:
        bells = Bells()
        bells.load_from_file(sys.argv[1])
    else:
        unittest.main()
