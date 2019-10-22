from ddt import ddt, data, unpack
from unittest import TestCase

from cached import util


@ddt
class TestClamp(TestCase):
    @data(
        (-1, 0, 3, 0),
        (0, 0, 3, 0),
        (1, 0, 3, 1),
        (2, 0, 3, 2),
        (3, 0, 3, 3),
        (4, 0, 3, 3),

        (0, -10, 10, 0),
        (-11, -10, 10, -10),
        (11, -10, 10, 10),
    )
    @unpack
    def test_clamp(self, value, min, max, expected):
        actual = util.clamp(value, min, max)
        self.assertEqual(expected, actual, 'The value should be clamped properly')
