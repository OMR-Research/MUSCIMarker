"""This module implements Grammars.

A Grammar is a set of rules about how objects form relationships.


"""
from __future__ import print_function, unicode_literals

import codecs
import logging
import os
import pprint
import re

import itertools

__version__ = "0.0.1"
__author__ = "Jan Hajic jr."


class DependencyGrammarParseError(Exception):
    pass


class DependencyGrammar(object):
    """The DependencyGrammar class implements rules about valid graphs above
    objects from a set of recognized classes.

    The Grammar complements a Parser. It defines rules, and the Parser
    implements algorithms to apply these rules to some input.

    A grammar has an **Alphabet** and **Rules**. The alphabet is a list
    of symbols that the grammar recognizes. Rules are constraints on
    the structures that can be induced among these symbols.

    There are two kinds of grammars according to what kinds of rules
    they use: **dependency** rules, and **constituency** rules. Dependency
    rules specify which symbols are governing, and which symbols are governed::

      notehead_full | stem

    There can be multiple left-hand side and right-hand side symbols,
    as a shortcut for a list of rules::

        notehead_full | stem beam
        notehead_full notehead_empty | ledger_line duration-dot tie grace_note

    The asterisk works as a wildcard. Currently, only one wildcard per symbol
    is allowed::

      time_signature | numeral_*

    Lines starting with a ``#`` are regarded as comments and ignored.
    Empty lines are also ignored.


    Constituency grammars consist of *rewriting rules*, such as::

      Note -> notehead stem | notehead stem duration-dot

    Constituency grammars also distinguish between *terminal* symbols, which
    can only occur on the right-hand side of the rules, and *non-terminal*
    symbols, which can also occur on the left-hand side. They are implemented
    in the class ``ConstituencyGrammar``.

    Cardinality rules
    -----------------

    We can also specify in the grammar the minimum and/or maximum number
    of relationships, both inlinks and outlinks, that an object can form
    with other objects of given types. For example:

    * One notehead may have up to two stems attached.
    * We also allow for stemless full noteheads.
    * One stem can be attached to multiple noteheads, but at least one.

    This would be expressed as::

      ``notehead-*{,2} | stem{1,}``

    The relationship of noteheads to ledger lines is generally ``m:n``::

      ``notehead-full | ledger_line``

    A time signature may consist of multiple numerals, but only one
    other symbol::

      time_signature{1,} | numeral_*{1}
      time_signature{1} | whole-time_mark alla_breve other_time_signature

    A key signature may have any number of sharps and flats.
    A sharp or flat can only belong to one key signature. However,
    not every sharp belongs to a key signature::

      key_signature | sharp{,1} flat{,1} natural{,1} double_sharp{,1} double_flat{,1}

    For the left-hand side of the rule, the cardinality restrictions apply to
    outlinks towards symbols of classes on the right-hand side of the rule.
    For the right-hand side, the cardinality restrictions apply to inlinks
    from symbols of left-hand side classes.

    It is also possible to specify that regardless of where outlinks
    lead, a symbol should always have at least some::

      time_signature{1,} |
      repeat{2,} |

    And analogously for inlinks:

      | letter_*{1,}
      | numeral_*{1,}
      | ledger_line{1,}
      | grace-notehead-*{1,}

    Interface
    ---------

    The basic role of the dependency grammar is to provide the list of rules:

    >>> from muscima.io import parse_mlclass_list
    >>> fpath = os.path.dirname(os.path.dirname(__file__)) + u'/data/grammars/mff-muscima-mlclasses-annot.deprules'
    >>> mlpath = os.path.dirname(os.path.dirname(__file__)) + u'/data/mff-muscima-mlclasses-annot.xml'
    >>> mlclass_dict = {m.clsid: m for m in parse_mlclass_list(mlpath)}
    >>> g = DependencyGrammar(grammar_filename=fpath, mlclasses=mlclass_dict)
    >>> len(g.rules)
    444

    Grammar I/O
    -----------

    The alphabet is stored by means of the already-familiar MLClassList.

    The rules are stored in *rule files*. For the grammars included
    in MUSCIMarker, rule files are stored in the ``data/grammars/``
    directory.

    A rule file line can be empty, start with a ``#`` (comment), or contain
    a rule symbol ``|``. Empty lines and comments are ignored during parsing.
    Rules are split into left- and right-hand side tokens, according to
    the position of the ``|`` symbol.

    Parsing a token returns the token string (unexpanded wildcards), its
    minimum and maximum cardinality in the rule (defaults are ``(0, 10000)``
    if no cardinality is provided).

    >>> g.parse_token(u'notehead-*')
    (u'notehead-*', 0, 10000)
    >>> g.parse_token(u'notehead-*{1,5}')
    (u'notehead-*', 1, 5)
    >>> g.parse_token(u'notehead-*{1,}')
    (u'notehead-*', 1, 10000)
    >>> g.parse_token(u'notehead-*{,5}')
    (u'notehead-*', 0, 5)
    >>> g.parse_token(u'notehead-*{1}')
    (u'notehead-*', 1, 1)

    The wildcards are expanded at the level of a line.

    >>> l = u'notehead-*{,2} | stem'
    >>> rules, inlink_cards, outlink_cards, _, _ = g.parse_dependency_grammar_line(l)
    >>> rules
    [(u'notehead-empty', u'stem'), (u'notehead-full', u'stem')]
    >>> outlink_cards[u'notehead-empty']
    {u'stem': (0, 2)}
    >>> inlink_cards[u'stem']
    {u'notehead-empty': (0, 10000), u'notehead-full': (0, 10000)}

    A key signature can have any number of sharps, flats, or naturals,
    but if a given symbol is part of a key signature, it can only be part of one.

    >>> l = u'key-signature | sharp{1} flat{1} natural{1}'
    >>> rules, inlink_cards, _, _, _ = g.parse_dependency_grammar_line(l)
    >>> rules
    [(u'key-signature', u'sharp'), (u'key-signature', u'flat'), (u'key-signature', u'natural')]
    >>> inlink_cards
    {u'sharp': {u'key-signature': (1, 1)}, u'natural': {u'key-signature': (1, 1)}, u'flat': {u'key-signature': (1, 1)}}

    You can also give *aggregate* cardinality rules, of the style "whatever rule
    applies, there should be at least X/at most Y edges for this type of object".

    >>> l = u'key-signature{1,} |'
    >>> _, _, _, _, out_aggregate_cards = g.parse_dependency_grammar_line(l)
    >>> out_aggregate_cards
    {u'key-signature': (1, 10000)}
    >>> l = u'grace-notehead*{1,} |'
    >>> _, _, _, _, out_aggregate_cards = g.parse_dependency_grammar_line(l)
    >>> out_aggregate_cards
    {u'grace-notehead-full': (1, 10000), u'grace-notehead-empty': (1, 10000)}
    >>> l = u'| beam{1,} stem{1,} flat{1,}'
    >>> _, _, _, in_aggregate_cards, _ = g.parse_dependency_grammar_line(l)
    >>> in_aggregate_cards
    {u'beam': (1, 10000), u'flat': (1, 10000), u'stem': (1, 10000)}

    """

    WILDCARD = '*'

    _MAX_CARD = 10000

    def __init__(self, grammar_filename, mlclasses):
        """Initialize the Grammar: fill in alphabet and parse rules."""
        self.alphabet = {unicode(m.name): m for m in mlclasses.values()}
        # logging.info('DependencyGrammar: got alphabet:\n{0}'
        #              ''.format(pprint.pformat(self.alphabet)))
        self.rules = []
        self.inlink_cardinalities = {}
        '''Keys: classes, values: dict of {from: (min, max)}'''

        self.outlink_cardinalities = {}
        '''Keys: classes, values: dict of {to: (min, max)}'''

        self.inlink_aggregated_cardinalities = {}
        '''Keys: classes, values: (min, max)'''

        self.outlink_aggregated_cardinalities = {}
        '''Keys: classes, values: (min, max)'''

        rules, ic, oc, iac, oac = self.parse_dependency_grammar_rules(grammar_filename)
        if self._validate_rules(rules):
            self.rules = rules
            logging.info('DependencyGrammar: Imported {0} rules'
                         ''.format(len(self.rules)))
            self.inlink_cardinalities = ic
            self.outlink_cardinalities = oc
            self.inlink_aggregated_cardinalities = iac
            self.outlink_aggregated_cardinalities = oac
            logging.debug('DependencyGrammar: Inlink aggregated cardinalities: {0}'
                          ''.format(pprint.pformat(iac)))
            logging.debug('DependencyGrammar: Outlink aggregated cardinalities: {0}'
                          ''.format(pprint.pformat(oac)))
        else:
            raise ValueError('Not able to parse dependency grammar file {0}.'
                             ''.format(grammar_filename))

    def validate_edge(self, head_name, child_name):
        return (head_name, child_name) in self.rules

    def validate_graph(self, vertices, edges):
        """Checks whether the given graph complies with the grammar.

        :param vertices: A dict with any keys and values corresponding
            to the alphabet of the grammar.

        :param edges: A list of ``(from, to)`` pairs, where both
            ``from`` and ``to`` are valid keys into the ``vertices`` dict.

        :returns: ``True`` if the graph is valid, ``False`` otherwise.
        """
        v, i, o = self.find_invalid_in_graph(vertices=vertices, edges=edges)
        return len(v) == 0

    def find_invalid_in_graph(self, vertices, edges, provide_reasons=False):
        """Finds vertices and edges where the given object graph does
        not comply with the grammar.

        Wrong vertices are any that:

        * are not in the alphabet;
        * have a wrong inlink or outlink;
        * have missing outlinks or inlinks.

        Discovering missing edges is difficult, because the grammar
        defines cardinalities on a per-rule basis and there is currently
        no way to make a rule compulsory, or to require at least one rule
        from a group to apply. It is currently not implemented.

        Wrong outlinks are such that:

        * connect symbol pairs that should not be connected based on their
          classes;
        * connect so that they exceed the allowed number of outlinks to
          the given symbol type

        Wrong inlinks are such that:

        * connect symbol pairs that should not be connected based on their
          classes;
        * connect so that they exceed the allowed number of inlinks
          to the given symbol based on the originating symbols' classes.

        :param vertices: A dict with any keys and values corresponding
            to the alphabet of the grammar.

        :param edges: A list of ``(from, to)`` pairs, where both
            ``from`` and ``to`` are valid keys into the ``vertices`` dict.

        :returns: A list of vertices, a list of inlinks and a list of outlinks
            that do not comply with the grammar.
        """
        logging.info('DependencyGrammar: looking for errors.')

        wrong_vertices = []
        wrong_inlinks = []
        wrong_outlinks = []

        reasons_v = {}
        reasons_i = {}
        reasons_o = {}

        # Check that vertices have labels that are in the alphabet
        for v, clsname in vertices.iteritems():
            if clsname not in self.alphabet:
                wrong_vertices.append(v)
                reasons_v[v] = 'Symbol {0} not in alphabet: class {1}.' \
                               ''.format(v, clsname)

        # Check that all edges are allowed
        for f, t in edges:
            nf, nt = unicode(vertices[f]), unicode(vertices[t])
            if (nf, nt) not in self.rules:
                logging.warning('Wrong edge: {0} --> {1}, rules:\n{2}'
                                ''.format(nf, nt, pprint.pformat(self.rules)))

                wrong_inlinks.append((f, t))
                reasons_i[(f, t)] = 'Outlink {0} ({1}) -> {2} ({3}) not in ' \
                                    'alphabet.'.format(nf, f, nt, t)

                wrong_outlinks.append((f, t))
                reasons_o[(f, t)] = 'Outlink {0} ({1}) -> {2} ({3}) not in ' \
                                    'alphabet.'.format(nf, f, nt, t)
                if f not in wrong_vertices:
                    wrong_vertices.append(f)
                    reasons_v[f] = 'Symbol {0} (class: {1}) participates ' \
                                   'in wrong outlink: {2} ({3}) --> {4} ({5})' \
                                   ''.format(f, vertices[f], nf, f, nt, t)
                if t not in wrong_vertices:
                    wrong_vertices.append(t)
                    reasons_v[t] = 'Symbol {0} (class: {1}) participates ' \
                                   'in wrong inlink: {2} ({3}) --> {4} ({5})' \
                                   ''.format(t, vertices[t], nf, f, nt, t)

        # Check aggregate cardinality rules
        #  - build inlink and outlink dicts
        inlinks = {}
        outlinks = {}
        for v in vertices:
            outlinks[v] = set()
            inlinks[v] = set()
        for f, t in edges:
            outlinks[f].add(t)
            inlinks[t].add(f)

        # If there are not enough edges, the vertex itself is wrong
        # (and none of the existing edges are wrong).
        # Currently, if there are too many edges, the vertex itself
        # is wrong and none of the existing edges are marked.
        #
        # Future:
        # If there are too many edges, the vertex itself and *all*
        # the edges are marked as wrong (because any of them is the extra
        # edge, and it's easiest to just delete them and start parsing
        # again).
        logging.debug('DependencyGrammar: checking outlink aggregate cardinalities'
                      '\n{0}'.format(pprint.pformat(outlinks)))
        for f in outlinks:
            f_clsname = vertices[f]
            if f_clsname not in self.outlink_aggregated_cardinalities:
                # Given vertex has no aggregate cardinality restrictions
                continue
            cmin, cmax = self.outlink_aggregated_cardinalities[f_clsname]
            logging.debug('DependencyGrammar: checking outlink cardinality'
                          ' rule fulfilled for vertex {0} ({1}): should be'
                          ' within {2} -- {3}'.format(f, vertices[f], cmin, cmax))
            if not (cmin <= len(outlinks[f]) <= cmax):
                wrong_vertices.append(f)
                reasons_v[f] = 'Symbol {0} (class: {1}) has {2} outlinks,' \
                               ' but grammar specifies {3} -- {4}.' \
                               ''.format(f, vertices[f], len(outlinks[f]),
                                         cmin, cmax)

        for t in inlinks:
            t_clsname = vertices[t]
            if t_clsname not in self.inlink_aggregated_cardinalities:
                continue
            cmin, cmax = self.inlink_aggregated_cardinalities[t_clsname]
            if not (cmin <= len(inlinks[t]) <= cmax):
                wrong_vertices.append(t)
                reasons_v[t] = 'Symbol {0} (class: {1}) has {2} inlinks,' \
                               ' but grammar specifies {3} -- {4}.' \
                               ''.format(f, vertices[f], len(inlinks[f]),
                                         cmin, cmax)

        # Now check for rule-based inlinks and outlinks.
        #for f in outlinks:
        #    oc = self.outlink_cardinalities[f]
        if provide_reasons:
            return wrong_vertices, wrong_inlinks, wrong_outlinks, \
                   reasons_v, reasons_i, reasons_o

        return wrong_vertices, wrong_inlinks, wrong_outlinks

    def parse_dependency_grammar_rules(self, filename):
        """Returns the Rules stored in the given rule file."""
        rules = []
        inlink_cardinalities = {}
        outlink_cardinalities = {}

        inlink_aggregated_cardinalities = {}
        outlink_aggregated_cardinalities = {}

        _invalid_lines = []
        with codecs.open(filename, 'r', 'utf-8') as hdl:
            for line_no, line in enumerate(hdl):
                l_rules, in_card, out_card, in_agg_card, out_agg_card = self.parse_dependency_grammar_line(line)

                if not self._validate_rules(l_rules):
                    _invalid_lines.append((line_no, line))

                rules.extend(l_rules)

                # Update cardinalities
                for lhs in out_card:
                    if lhs not in outlink_cardinalities:
                        outlink_cardinalities[lhs] = dict()
                    outlink_cardinalities[lhs].update(out_card[lhs])

                for rhs in in_card:
                    if rhs not in inlink_cardinalities:
                        inlink_cardinalities[rhs] = dict()
                    inlink_cardinalities[rhs].update(in_card[rhs])

                inlink_aggregated_cardinalities.update(in_agg_card)
                outlink_aggregated_cardinalities.update(out_agg_card)

        if len(_invalid_lines) > 0:
            logging.warning('DependencyGrammar.parse_rules(): Invalid lines'
                            ' {0}'.format(pprint.pformat(_invalid_lines)))

        return rules, inlink_cardinalities, outlink_cardinalities, \
               inlink_aggregated_cardinalities, outlink_aggregated_cardinalities

    def parse_dependency_grammar_line(self, line):
        """Parse one dependency grammar line. See DependencyGrammar
        I/O documentation for the format."""
        rules = []
        out_cards = {}
        in_cards = {}
        out_agg_cards = {}
        in_agg_cards = {}

        if line.strip().startswith('#'):
            return [], dict(), dict(), dict(), dict()
        if len(line.strip()) == 0:
            return [], dict(), dict(), dict(), dict()
        if '|' not in line:
            return [], dict(), dict(), dict(), dict()

        # logging.info('DependencyGrammar: parsing rule line:\n\t\t{0}'
        #              ''.format(line.rstrip('\n')))
        lhs, rhs = line.strip().split('|', 1)
        lhs_tokens = lhs.strip().split()
        rhs_tokens = rhs.strip().split()

        #logging.info('DependencyGrammar: tokens lhs={0}, rhs={1}'
        #             ''.format(lhs_tokens, rhs_tokens))

        # Normal rule line? Aggregate cardinality line?
        _line_type = 'normal'
        if len(lhs) == 0:
            _line_type = 'aggregate_inlinks'
        if len(rhs) == 0:
            _line_type = 'aggregate_outlinks'

        logging.debug('Line {0}: type {1}, lhs={2}, rhs={3}'.format(line, _line_type, lhs, rhs))

        if _line_type == 'aggregate_inlinks':
            rhs_tokens = rhs.strip().split()
            for rt in rhs_tokens:
                token, rhs_cmin, rhs_cmax = self.parse_token(rt)
                for t in self._matching_names(token):
                    in_agg_cards[t] = (rhs_cmin, rhs_cmax)
            logging.debug('DependencyGrammar: found inlinks: {0}'
                          ''.format(pprint.pformat(in_agg_cards)))
            return rules, out_cards, in_cards, in_agg_cards, out_agg_cards

        if _line_type == 'aggregate_outlinks':
            lhs_tokens = lhs.strip().split()
            for lt in lhs_tokens:
                token, lhs_cmin, lhs_cmax = self.parse_token(lhs.strip())
                for t in self._matching_names(token):
                    out_agg_cards[t] = (lhs_cmin, lhs_cmax)
            logging.debug('DependencyGrammar: found outlinks: {0}'
                          ''.format(pprint.pformat(out_agg_cards)))
            return rules, out_cards, in_cards, in_agg_cards, out_agg_cards

        # Normal line that defines a left-hand side and a right-hand side

        lhs_symbols = []
        # These cardinalities apply to all left-hand side tokens,
        # for edges leading to any of the right-hand side tokens.
        lhs_cards = {}
        for l in lhs_tokens:
            token, lhs_cmin, lhs_cmax = self.parse_token(l)
            all_tokens = self._matching_names(token)
            lhs_symbols.extend(all_tokens)
            for t in all_tokens:
                lhs_cards[t] = (lhs_cmin, lhs_cmax)

        rhs_symbols = []
        rhs_cards = {}
        for r in rhs_tokens:
            token, rhs_cmin, rhs_cmax = self.parse_token(r)
            all_tokens = self._matching_names(token)
            rhs_symbols.extend(all_tokens)
            for t in all_tokens:
                rhs_cards[t] = (rhs_cmin, rhs_cmax)

        # logging.info('DependencyGrammar: symbols lhs={0}, rhs={1}'
        #              ''.format(lhs_symbols, rhs_symbols))

        # Build the outputs from the cartesian product
        # of left-hand and right-hand tokens.
        for l in lhs_symbols:
            if l not in out_cards:
                out_cards[l] = {}
            for r in rhs_symbols:
                if r not in in_cards:
                    in_cards[r] = {}

                rules.append((l, r))
                out_cards[l][r] = lhs_cards[l]
                in_cards[r][l] = rhs_cards[r]

        # logging.info('DependencyGramamr: got rules:\n{0}'
        #              ''.format(pprint.pformat(rules)))
        # logging.info('DependencyGrammar: got inlink cardinalities:\n{0}'
        #              ''.format(pprint.pformat(in_cards)))
        # logging.info('DependencyGrammar: got outlink cardinalities:\n{0}'
        #              ''.format(pprint.pformat(out_cards)))
        return rules, in_cards, out_cards, in_agg_cards, out_agg_cards

    def parse_token(self, l):
        """Parse one *.deprules file token. See class documentation for
        examples.

        :param l: One token of a *.deprules file.

        :return: token, cmin, cmax
        """
        l = unicode(l)
        cmin, cmax = 0, self._MAX_CARD
        if '{' not in l:
            token = l
        else:
            token, cardinality = l[:-1].split('{')
            if ',' not in cardinality:
                cmin, cmax = int(cardinality), int(cardinality)
            else:
                cmin_string, cmax_string = cardinality.split(',')
                if len(cmin_string) > 0:
                    cmin = int(cmin_string)
                if len(cmax_string) > 0:
                    cmax = int(cmax_string)
        return token, cmin, cmax

    def _matching_names(self, token):
        """Returns the list of alphabet symbols that match the given
        name (regex, currently can process one '*' wildcard).

        :type token: str
        :param token: The symbol name (pattern) to expand.

        :rtype: list
        :returns: A list of matching names. Empty list if no name matches.
        """
        if not self._has_wildcard(token):
            return [token]

        wildcard_idx = token.index(self.WILDCARD)
        prefix = token[:wildcard_idx]
        if wildcard_idx < len(token) - 1:
            suffix = token[wildcard_idx+1:]
        else:
            suffix = ''

        # logging.info('DependencyGrammar._matching_names: token {0}, pref={1}, suff={2}'
        #              ''.format(token, prefix, suffix))

        matching_names = self.alphabet.keys()
        if len(prefix) > 0:
            matching_names = [n for n in matching_names if n.startswith(prefix)]
        if len(suffix) > 0:
            matching_names = [n for n in matching_names if n.endswith(suffix)]

        return matching_names

    def _validate_rules(self, rules):
        """Check that all the rules are valid under the current alphabet."""
        missing_heads = set()
        missing_children = set()
        for h, ch in rules:
            if h not in self.alphabet:
                missing_heads.add(h)
            if ch not in self.alphabet:
                missing_children.add(ch)

        if (len(missing_heads) + len(missing_children)) > 0:
            logging.warning('DependencyGrammar.validate_rules: missing heads '
                            '{0}, children {1}'
                            ''.format(missing_heads, missing_children))
            return False
        else:
            return True

    def _has_wildcard(self, name):
        return self.WILDCARD in name

    def is_head(self, head, child):
        return (head, child) in self.rules


##############################################################################

