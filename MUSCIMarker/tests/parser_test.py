import unittest
import os

from muscima.io import parse_cropobject_class_list
from MUSCIMarker.syntax.dependency_grammar import DependencyGrammar

class DependencyGrammarTest(unittest.TestCase):
    def test_grammar_parsing(self):
        fpath = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             'data/grammars/mff-muscima-mlclasses-annot.deprules')
        mlpath = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data/mff-muscima-mlclasses-annot.xml')
        mlclass_dict = {m.clsid: m for m in parse_cropobject_class_list(mlpath)}
        g = DependencyGrammar(grammar_filename=fpath, mlclasses=mlclass_dict)
        length = len(g.rules)

        self.assertEqual(622, length)


if __name__ == '__main__':
    unittest.main()
