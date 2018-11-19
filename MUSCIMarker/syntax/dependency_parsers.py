"""This module implements a class that..."""
from __future__ import print_function, unicode_literals

from builtins import object
import collections
import logging

import numpy
from mung.node import cropobject_distance
from mung.graph import find_beams_incoherent_with_stems
from mung.inference.constants import _CONST
from sklearn.feature_extraction import DictVectorizer

__version__ = "0.0.1"
__author__ = "Jan Hajic jr."


class SimpleDeterministicDependencyParser(object):
    """This dependency parser just adds all possible edges,
    as defined by the given grammar."""
    def __init__(self, grammar):
        """Initialize the parser.

        :type grammar: DependencyGrammar
        :param grammar: A DependencyGrammar.
        """
        logging.info('SimpleDeterministicDependencyParser: Initializing parser.')
        self.grammar = grammar

    def parse(self, cropobjects):
        """Adds all edges allowed by the grammar, given the list
        of symbols. The edges are (i, j) tuples of indices into the
        supplied list of symbol names.
        """
        symbol_names = [c.clsname for c in cropobjects]
        symbol_name_idxs = self.get_all_possible_edges(symbol_names)
        edges = [(cropobjects[i].objid, cropobjects[j].objid) for i, j in symbol_name_idxs]
        return edges

    def get_all_possible_edges(self, symbol_names):
        """Collects all symbol edges that are permissible, using the grammar.

        :rtype: list
        :returns: A list of ``(i, j)`` tuples, where ``i`` and ``j``
            are indices into the list of symbol names (so that whoever
            provided the names can track down the specific objects
            from which the symbol names were collected - there is no
            requirement that the names must be unique).
        """
        edges = []

        for i, s1, in enumerate(symbol_names):
            for j, s2 in enumerate(symbol_names):
                if self.grammar.is_head(s1, s2):
                    # No loops!
                    if i != j:
                        edges.append((i, j))

        return edges

    def set_grammar(self, grammar):
        # More complex parsers might need to reset some internal states
        self.grammar = grammar


class PairwiseClassificationParser(object):
    """This parser applies a simple classifier that takes the bounding
    boxes of two MungNodes and their classes and returns whether there
    is an edge or not."""
    MAXIMUM_DISTANCE_THRESHOLD = 200

    def __init__(self, grammar, clf, cropobject_feature_extractor):
        self.grammar = grammar
        self.clf = clf
        self.extractor = cropobject_feature_extractor

    def parse(self, cropobjects):

        # Ensure the same docname for all cropobjects,
        # since we later compute their distances.
        # The correct docname gets set on export anyway.
        default_doc = cropobjects[0].doc
        for c in cropobjects:
            c.set_doc(default_doc)

        pairs, features = self.extract_all_pairs(cropobjects)

        logging.info('Clf.Parse: {0} object pairs from {1} objects'.format(len(pairs), len(cropobjects)))

        preds = self.clf.predict(features)

        edges = []
        for idx, (c_from, c_to) in enumerate(pairs):
            if preds[idx] != 0:
                edges.append((c_from.objid, c_to.objid))

        edges = self._apply_trivial_fixes(cropobjects, edges)
        return edges

    def _apply_trivial_fixes(self, cropobjects, edges):
        edges = self._only_one_stem_per_notehead(cropobjects, edges)
        edges = self._every_full_notehead_has_a_stem(cropobjects, edges)

        return edges

    def _only_one_stem_per_notehead(self, cropobjects, edges):
        _cdict = {c.objid: c for c in cropobjects}

        # Collect stems per notehead
        stems_per_notehead = collections.defaultdict(list)
        stem_objids = set()
        for f_objid, t_objid in edges:
            f = _cdict[f_objid]
            t = _cdict[t_objid]
            if (f.clsname in _CONST.NOTEHEAD_CLSNAMES) and \
                (t.clsname == 'stem'):
                stems_per_notehead[f_objid].append(t_objid)
                stem_objids.add(t_objid)

        # Pick the closest one (by minimum distance)
        closest_stems_per_notehead = dict()
        for n_objid in stems_per_notehead:
            n = _cdict[n_objid]
            stems = [_cdict[objid] for objid in stems_per_notehead[n_objid]]
            closest_stem = min(stems, key=lambda s: cropobject_distance(n, s))
            closest_stems_per_notehead[n_objid] = closest_stem.objid

        # Filter the edges
        edges = [(f_objid, t_objid) for f_objid, t_objid in edges
                 if (f_objid not in closest_stems_per_notehead) or
                    (t_objid not in stem_objids) or
                    (closest_stems_per_notehead[f_objid] == t_objid)]

        return edges

    def _every_full_notehead_has_a_stem(self, cropobjects, edges):
        _cdict = {c.objid: c for c in cropobjects}

        # Collect stems per notehead
        notehead_objids = set([c.objid for c in cropobjects if c.clsname == 'notehead-full'])
        stem_objids = set([c.objid for c in cropobjects if c.clsname == 'stem'])

        noteheads_with_stem_objids = set()
        stems_with_notehead_objids = set()
        for f, t in edges:
            if _cdict[f].clsname == 'notehead-full':
                if _cdict[t].clsname == 'stem':
                    noteheads_with_stem_objids.add(f)
                    stems_with_notehead_objids.add(t)

        noteheads_without_stems = {n: _cdict[n] for n in notehead_objids
                                      if n not in noteheads_with_stem_objids}
        stems_without_noteheads = {n: _cdict[n] for n in stem_objids
                                      if n not in stems_with_notehead_objids}

        # To each notehead, assign the closest stem that is not yet taken.
        closest_stem_per_notehead = {objid: min(stems_without_noteheads,
                                            key=lambda x: cropobject_distance(_cdict[x], n))
                                     for objid, n in list(noteheads_without_stems.items())}

        # Filter edges that are too long
        _n_before_filter = len(closest_stem_per_notehead)
        closest_stem_threshold_distance = 80
        closest_stem_per_notehead = {n_objid: s_objid
                                     for n_objid, s_objid in list(closest_stem_per_notehead.items())
                                     if cropobject_distance(_cdict[n_objid],
                                                            _cdict[s_objid])
                                         < closest_stem_threshold_distance
                                     }


        return edges + list(closest_stem_per_notehead.items())

    def extract_all_pairs(self, cropobjects):
        pairs = []
        features = []
        for u in cropobjects:
            for v in cropobjects:
                if u.objid == v.objid:
                    continue
                distance = cropobject_distance(u, v)
                if distance < self.MAXIMUM_DISTANCE_THRESHOLD:
                    pairs.append((u, v))
                    f = self.extractor(u, v)
                    features.append(f)

        # logging.info('Parsing features: {0}'.format(features[0]))
        features = numpy.array(features)
        # logging.info('Parsing features: {0}/{1}'.format(features.shape, features))
        return pairs, features

    def is_edge(self, c_from, c_to):
        features = self.extractor(c_from, c_to)
        result = self.clf.predict(features)
        return result

    def set_grammar(self, grammar):
        self.grammar = grammar

##############################################################################
# Feature extraction

class PairwiseClfFeatureExtractor(object):
    def __init__(self, vectorizer=None):
        """Initialize the feature extractor.

        :param vectorizer: A DictVectorizer() from scikit-learn.
            Used to convert feature dicts to the vectors that
            the edge classifier of the parser will expect.
            If None, will create a new DictVectorizer. (This is useful
            for training; you can then pickle the entire extractor
            and make sure the feature extraction works for the classifier
            at runtime.)
        """
        if vectorizer is None:
            vectorizer = DictVectorizer()
        self.vectorizer = vectorizer

    def __call__(self, *args, **kwargs):
        """The call is per item (in this case, MungNode pair)."""
        fd = self.get_features_relative_bbox_and_clsname(*args, **kwargs)
        # Compensate for the vecotrizer "target", which we don't have here (by :-1)
        item_features = self.vectorizer.transform(fd).toarray()[0, :-1]
        return item_features

    def get_features_relative_bbox_and_clsname(self, c_from, c_to):
        """Extract a feature vector from the given pair of MungNodes.
        Does *NOT* convert the class names to integers.

        Features: bbox(c_to) - bbox(c_from), clsname(c_from), clsname(c_to)
        Target: 1 if there is a link from u to v

        Returns a dict that works as input to ``self.vectorizer``.
        """
        target = 0
        if c_from.doc == c_to.doc:
            if c_to.objid in c_from.outlinks:
                target = 1
        features = (c_to.top - c_from.top,
                    c_to.left - c_from.left,
                    c_to.bottom - c_from.bottom,
                    c_to.right - c_from.right,
                    c_from.clsname,
                    c_to.clsname,
                    target)
        dt, dl, db, dr, cu, cv, tgt = features
        # Normalizing clsnames
        if cu.startswith('letter'): cu = 'letter'
        if cu.startswith('numeral'): cu = 'numeral'
        if cv.startswith('letter'): cv = 'letter'
        if cv.startswith('numeral'): cv = 'numeral'
        feature_dict = {'dt': dt,
                        'dl': dl,
                        'db': db,
                        'dr': dr,
                        'cls_from': cu,
                        'cls_to': cv,
                        'target': tgt}
        return feature_dict

    def get_features_distance_relative_bbox_and_clsname(self, c_from, c_to):
        """Extract a feature vector from the given pair of MungNodes.
        Does *NOT* convert the class names to integers.

        Features: bbox(c_to) - bbox(c_from), clsname(c_from), clsname(c_to)
        Target: 1 if there is a link from u to v

        Returns a tuple.
        """
        target = 0
        if c_from.doc == c_to.doc:
            if c_to.objid in c_from.outlinks:
                target = 1
        distance = cropobject_distance(c_from, c_to)
        features = (distance,
                    c_to.top - c_from.top,
                    c_to.left - c_from.left,
                    c_to.bottom - c_from.bottom,
                    c_to.right - c_from.right,
                    c_from.clsname,
                    c_to.clsname,
                    target)
        dist, dt, dl, db, dr, cu, cv, tgt = features
        if cu.startswith('letter'): cu = 'letter'
        if cu.startswith('numeral'): cu = 'numeral'
        if cv.startswith('letter'): cv = 'letter'
        if cv.startswith('numeral'): cv = 'numeral'
        feature_dict = {'dist': dist,
                        'dt': dt,
                        'dl': dl,
                        'db': db,
                        'dr': dr,
                        'cls_from': cu,
                        'cls_to': cv,
                        'target': tgt}
        return feature_dict

