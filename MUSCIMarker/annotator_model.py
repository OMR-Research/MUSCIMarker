"""This module implements a class that..."""
from __future__ import print_function, unicode_literals

from builtins import str
import codecs
import itertools
import logging
import os
import pickle
import traceback
import uuid

# import cv2
# import matplotlib.pyplot as plt
import numpy
from scipy.misc import imsave

from kivy.app import App
from kivy.properties import ObjectProperty, DictProperty, NumericProperty, ListProperty, StringProperty
from kivy.uix.widget import Widget

from mung.io import export_cropobject_list
import mung.stafflines
from mung.inference.inference import PitchInferenceEngine, OnsetsInferenceEngine, MIDIBuilder, play_midi
from mung.inference.constants import InferenceEngineConstants as _CONST
from mung.graph import \
    find_beams_incoherent_with_stems, \
    find_misdirected_ledger_line_edges, \
    find_related_staffs
from MUSCIMarker.object_detection import ObjectDetectionHandler
from MUSCIMarker.syntax.dependency_parsers import SimpleDeterministicDependencyParser, PairwiseClassificationParser, \
    PairwiseClfFeatureExtractor
from MUSCIMarker.utils import compute_connected_components
from MUSCIMarker.tracker import Tracker

from MUSCIMarker.image_processing import ImageProcessing


__version__ = "0.0.1"
__author__ = "Jan Hajic jr."


class ObjectGraph(Widget):
    """This class describes how the MungNodes from
    a CropObjectAnnotatorModel are attached to each other,
    forming an oriented graph.

    The Graph model never actually interacts with the MungNodes
    that form its nodes. It is only aware of their ``objid``s.
    The interaction with MungNodes is only necessary during rendering.
    """

    # cropobject_model = ObjectProperty()
    # '''Reference to the CropObjcetAnnotatorModel holding MungNode
    # information.'''
    vertices = DictProperty()
    '''List of valid vertex indices.'''

    edges = DictProperty()
    '''Attachments among symbols are dependency relationships, such as
    between a notehead and a stem. We store attachments as oriented
    edges.

    An attachment is represented as a ``(objid_1, objid_2)`` key with
    a value of ``True``.
    '''

    _outlinks = DictProperty()
    '''Automatically computed dict of all MungNodes attached to a given
    MungNode. Internal.'''

    _inlinks = DictProperty()
    '''Automatically computed dict of all MungNodes that the given
    MungNode is attached to. Internal.'''

    # def __init__(self, model, **kwargs):
    #     super(ObjectGraph, self).__init__(**kwargs)
    #     # self.cropobject_model = model
    #     # model.sync_cropobjects_to_graph()

    ##########################################################################
    # Managing the attachments

    def add_vertex(self, v):
        self.vertices[v] = True

    def remove_vertex(self, v):
        if v in self.vertices:
            self.remove_obj_from_graph(v)

    def ensure_add_edge(self, edge, label='Attachment'):
        logging.info('Graph: ensuring edge {0}'.format(edge))
        if edge not in self.edges:
            self.add_edge(edge, label=label)

    def add_edge(self, edge, label='Attachment'):
        """Edge is an ``(a1, a2)`` pair such that ``a1`` is the head
        and ``a2`` is the child MungNode. Our (attachment) dependency edges
        lead from the root down, at least in the model."""
        logging.info('Graph: adding edge {0} with label {1}'.format(edge, label))
        a1 = edge[0]
        a2 = edge[1]

        if a1 == a2:
            logging.warn('Requested adding loop {0}-{1}; cannot add loops!'.format(a1, a2))
            return

        if a1 not in self.vertices:
            raise ValueError('Invalid attachment {0}: member {1} not in cropobjects.'
                             ''.format(edge, a1))
        if a2 not in self.vertices:
            raise ValueError('Invalid attachment {0}: member {1} not in cropobjects.'
                             ''.format(edge, a2))

        self.edges[edge] = label
        self.add_to_edges_index(a1, a2)

    def ensure_add_edges(self, edges, label='Attachment'):
        logging.info('Graph: ensuring edges {0}'.format(edges))
        edges_to_add = [e for e in edges if e not in self.edges]
        self.add_edges(edges_to_add, label=label)

    def add_edges(self, edges, label='Attachment'):
        logging.info('Graph: adding {0} edges with label {1}'
                     ''.format(len(edges), label))

        # First add to edges index
        for a1, a2 in edges:
            if a1 == a2:
                logging.warn('Requested adding loop {0}-{1}; cannot add loops!'.format(a1, a2))
                continue

            if a1 not in self.vertices:
                raise ValueError('Invalid attachment {0}: member {1} not in cropobjects.'
                                 ''.format((a1, a2), a1))
            if a2 not in self.vertices:
                raise ValueError('Invalid attachment {0}: member {1} not in cropobjects.'
                                 ''.format((a1, a2), a2))
            self.add_to_edges_index(a1, a2)

        edge_dict = {e: label for e in edges}
        self.edges.update(edge_dict)

    def add_to_edges_index(self, a1, a2):
        if a1 not in self._outlinks:
            self._outlinks[a1] = set()
        if a2 not in self._inlinks:
            self._inlinks[a2] = set()

        if a2 not in self._outlinks[a1]:
            self._outlinks[a1].add(a2)
        else:
            logging.warn('Trying to re-add outlink from {0} to {1}'
                         ''.format(a1, a2))
        if a1 not in self._inlinks[a2]:
            self._inlinks[a2].add(a1)
        else:
            logging.warn('Trying to re-add inlink from {0} to {1}'
                         ''.format(a1, a2))

    def compute_edges_index(self, attachments):
        '''Adds to the attachment indexes all the given
        attachments ``(a1, a2)``.'''
        for a1, a2 in attachments:
            self.add_to_edges_index((a1, a2))

    def ensure_remove_edge(self, a1, a2):
        """If there was an edge from a1 to a2, remove it."""
        logging.info('Model: ensuring detaching edge from {0} to {1}'
                     ''.format(a1, a2))
        if (a1, a2) in self.edges:
            self.remove_edge(a1, a2)

    def remove_edge(self, a1, a2):
        """Object a1 will no longer point at object a2."""
        if a2 not in self._inlinks:
            logging.warn('Edge {0} --> {1}: {1} not in self._inlinks!'
                         ''.format(a1, a2))
        elif a1 not in self._inlinks[a2]:
            logging.warn('Edge {0} --> {1}: not found in inlinks of {1}'
                         ''.format(a1, a2))
        else:
            self._inlinks[a2].remove(a1)

        if a1 not in self._outlinks:
            logging.warn('Edge {0} --> {1}: {0} not in self._outlinks!!'
                         ''.format(a1, a2))
        elif a2 not in self._outlinks[a1]:
            logging.warn('Edge {0} --> {1}: not found in outlinks of {0}'
                         ''.format(a1, a2))
        else:
            self._outlinks[a1].remove(a2)
        del self.edges[a1, a2]

    def remove_obj_from_graph(self, objid):
        """Clears out the given MungNode from the attachments
        graph.

        DO NOT USE THIS if you only want to clear out the object's
        edges. This is used when the object disappears from the
        vertices as well.
        """
        self.remove_obj_edges(objid)
        del self.vertices[objid]

    def remove_obj_edges(self, objid):
        """Clears all edges in which the object participates."""
        if objid in self._inlinks:
            inlinks = self._inlinks[objid]
            for a in inlinks:
                del self.edges[a, objid]

        if objid in self._outlinks:
            outlinks = self._outlinks[objid]
            for a in outlinks:
                del self.edges[objid, a]

        self._remove_obj_from_edges_index(objid)

    def _remove_obj_from_edges_index(self, objid):
        """Remove all of this node's inlinks and outlinks,
        and remove its record from the attachment index.
        DO NOT USE THIS directly, use :meth:`remove_obj_from_attachment`!"""
        if objid in self._outlinks:
            self._clear_obj_outlinks(objid)
            del self._outlinks[objid]
        if objid in self._inlinks:
            self._clear_obj_inlinks(objid)
            del self._inlinks[objid]

    def _clear_obj_outlinks(self, objid):
        """Remove the node's outlinks, and remove it from the inlinks
        of the nodes it outlinks to."""
        if objid in self._outlinks:
            outlinks = self._outlinks[objid]
            for o in outlinks:
                if objid in self._inlinks[o]:
                    self._inlinks[o].remove(objid)
            self._outlinks[objid] = set()

    def _clear_obj_inlinks(self, objid):
        """Remove the node's inlinks, and remove it from the outlinks
        of the nodes from which it has inlinks"""
        if objid in self._inlinks:
            inlinks = self._inlinks[objid]
            for i in inlinks:
                if objid in self._outlinks[i]:
                    self._outlinks[i].remove(objid)
            self._inlinks[objid] = set()

    def clear(self):
        self.vertices = []
        self.clear_edges()

    def clear_edges(self):
        self.edges = {}
        self._inlinks = dict()
        self._outlinks = dict()

    def get_neighborhood(self, objid, inclusive=True):
        """Returns a list of ``objid``s of the undirected neighbors
        of the given object. Useful e.g. for only removing [...?]

        :param objid: Object ID of the "center" of the neighborhood

        :param inclusive: Should the output include the "center" object?
        """
        neighbors = []
        if inclusive:
            neighbors.append(objid)
        if objid in self._inlinks:
            neighbors.extend(self._inlinks[objid])
        if objid in self._outlinks:
            neighbors.extend(self._outlinks[objid])
        return list(set(neighbors))     # Removing duplicates

    def inlinks_of(self, objid, label=None):
        """Returns the inlinks for the given objid such that the
        edges are labeled with the given label. If the label
        is ``None``, then all inlinks are returned regardless of
        their labels.

        :returns: List of ``objid``s of inlinks with given label.
            Empty list if no such inlinks exist in graph.
        """
        if objid not in self._inlinks:
            return []

        if label is None:
            return list(self._inlinks[objid])

        output = []
        for i in list(self._inlinks[objid]):
            if self.edges[(i, objid)] == label:
                output.append(i)

        return output

    def outlinks_of(self, objid, label=None):
        """Returns the outlinks for the given objid such that the
        edges are labeled with the given label. If the label
        is ``None``, then all outlinks are returned regardless of
        their labels.

        :returns: List of ``objid``s of outlinks with given label.
            Empty list if no such inlinks exist in graph.
        """
        if objid not in self._outlinks:
            return []

        if label is None:
            return list(self._outlinks[objid])

        output = []
        for o in list(self._outlinks[objid]):
            if self.edges[(objid, o)] == label:
                output.append(o)

        return output


##############################################################################


class CropObjectAnnotatorModel(Widget):
    """This model describes the conceptual interface of the annotation
    app: there is an annotator performing some actions, and this model
    has support for these actions. It operates with finished MungNodes
    and MLClasses.

    The annotator is working with three sets of objects:

    * The image that is being annotated,
    * the MungNodes that have already been marked,
    * the set of object types that can be marked.

    The object graph is synced to the MungNode dict in the Model
    on export.

    """
    image = ObjectProperty()

    # Connected component precomputing
    _cc = NumericProperty(-1)
    _labels = ObjectProperty(None, allownone=True)
    _bboxes = ObjectProperty(None, allownone=True)

    cropobjects = DictProperty()
    mlclasses = DictProperty()
    mlclasses_by_name = DictProperty()

    graph = ObjectProperty()

    parser = ObjectProperty(None, allownone=True)
    backup_parser = ObjectProperty(None, allownone=True)
    grammar = ObjectProperty(None, allownone=True)

    _current_tmp_image_filename = StringProperty(None, allownone=True)

    _image_processor = ImageProcessing()

    # Object detection
    _object_detection_client = ObjectProperty(None, allownone=True)



    def __init__(self, image=None, cropobjects=None, mlclasses=None, **kwargs):
        super(CropObjectAnnotatorModel, self).__init__(**kwargs)

        self.image = image
        self.cropobjects = dict()
        if cropobjects:
            self.import_cropobjects(cropobjects)
        self.mlclasses = dict()
        self.mlclasses_by_name = dict()
        if mlclasses:
            self.import_classes_definition(mlclasses)

        self.graph = ObjectGraph()
        self.sync_cropobjects_to_graph()

        # self._init_object_detection_handler()
        # ...only run this once the app is running.

    def init_object_detection_handler(self):
        config = App.get_running_app().config

        port = int(config.get('symbol_detection_client', 'port'))
        hostname = config.get('symbol_detection_client', 'hostname')

        self._object_detection_client = ObjectDetectionHandler(
            tmp_dir=App.get_running_app().tmp_dir,
            port=port,
            hostname=hostname)

        self._object_detection_client.bind(result=self.process_detection_result)

    def init_parser(self, grammar):
        config = App.get_running_app().config
        smart_parsing = (config.get('parsing', 'smart_parsing') == '1')
        logging.info('Initializing parser: Smart parsing = {0}'.format(smart_parsing))
        if smart_parsing:

            vectorizer_file = config.get('parsing', 'smart_parsing_vectorizer')
            with open(vectorizer_file, 'rb') as hdl:
                vectorizer = pickle.load(hdl, encoding='latin2')
            feature_extractor = PairwiseClfFeatureExtractor(vectorizer=vectorizer)

            model_file = config.get('parsing', 'smart_parsing_model')
            with open(model_file, 'rb') as hdl:
                classifier = pickle.load(hdl, encoding='latin2')

            self.parser = PairwiseClassificationParser(grammar=grammar,
                                                       clf=classifier,
                                                       cropobject_feature_extractor=feature_extractor)

        else:
            self.parser = SimpleDeterministicDependencyParser(grammar=grammar)
        self.backup_parser = SimpleDeterministicDependencyParser(grammar=grammar)

    def load_image(self, image, compute_cc=False, do_preprocessing=True,
                   update_temp=True):
        self._invalidate_cc_cache()

        # Apply preprocessing
        if do_preprocessing:
            processed_image = self._image_processor.process(image)
        else:
            processed_image = image
        self.image = processed_image

        if compute_cc:
            self._compute_cc_cache()

        if update_temp:
            self._update_temp_image()

    def _update_temp_image(self):
        new_temp_fname = self._generate_model_image_tmp_filename()
        if self._current_tmp_image_filename is not None:
            if os.path.isfile(self._current_tmp_image_filename):
                os.unlink(self._current_tmp_image_filename)

        imsave(new_temp_fname, self.image)
        self._current_tmp_image_filename = new_temp_fname

    def _generate_model_image_tmp_filename(self):
        tmpdir = App.get_running_app().tmp_dir
        random_string = str(uuid.uuid4())[:8]
        tmp_fname = os.path.join(tmpdir, 'current_model_image__{0}.png'
                                         ''.format(random_string))
        return tmp_fname

    @Tracker(track_names=['cropobject'],
             transformations={'cropobject': [lambda c: ('objid', c.objid),
                                             lambda c: ('clsname', c.clsname),
                                             lambda c: ('tool_used', App.get_running_app().currently_selected_tool_name)]
                              },
             fn_name='model.add_cropobject',
             tracker_name='model')
    def add_cropobject(self, cropobject, perform_checks=True):
        if perform_checks:
            if not self._is_cropobject_valid(cropobject):
                logging.info('Model: Adding cropobject {0}: invalid!'
                             ''.format(cropobject.objid))
                return

        # Sync added cropobject to graph
        self.graph.add_vertex(cropobject.objid)
        # collect edges & add them at once
        edges = []
        for i in cropobject.inlinks:
            edges.append((i, cropobject.objid))
        for o in cropobject.outlinks:
            edges.append((cropobject.objid, o))
        #logging.info('Model: Adding cropobject {0}: Will add edges: {1}'
        #             ''.format(cropobject.objid, edges))
        self.graph.add_edges(edges)

        self.cropobjects[cropobject.objid] = cropobject

        # Sync graph: the object might add inlinks/outlinks
        # to other objects.
        self.sync_graph_to_cropobjects()

    def _is_cropobject_valid(self, cropobject):
        t, l, b, r = cropobject.bounding_box
        if (b - t) * (r - l) < 10:
            logging.warn('Model: Trying to add a MungNode that is very small'
                         ' ({0} x {1})'.format(cropobject.height, cropobject.width))
            return False
        return True

    @Tracker(track_names=['key'],
             transformations={'key': [lambda key: ('objid', key)]},
             fn_name='model.remove_cropobject',
             tracker_name='model')
    def remove_cropobject(self, key):
        # Could graph sync be solved by binding?
        neighborhood = [self.cropobjects[k]
             for k in self.graph.get_neighborhood(key, inclusive=True)]
        self.graph.remove_obj_from_graph(key)
        self.sync_graph_to_cropobjects(neighborhood)
        del self.cropobjects[key]

    @Tracker(track_names=['cropobjects'],
             transformations={'cropobjects': [lambda c: ('n_cropobjects', len(c)),
                                              lambda cs: ('objids', [c.objid for c in cs])]},
             fn_name='model.import_cropobjects',
             tracker_name='model')
    def import_cropobjects(self, cropobjects, clear=True):
        logging.info('Model: Importing {0} cropobjects.'.format(len(cropobjects)))
        if clear:
            self.clear_cropobjects()
        # Batch processing is more efficient, since rendering the CropObjectList
        # is tied to any change of self.cropobjects
        self.cropobjects = {c.objid: c for c in cropobjects}
        # self.ensure_cropobjects_consistent()
        self.sync_cropobjects_to_graph()
        # self.ensure_consistent()

    @Tracker(track_names=[],
             fn_name='model.export_cropobjects_string',
             tracker_name='model')
    def export_cropobjects_string(self, **kwargs):
        self.sync_graph_to_cropobjects()
        return export_cropobject_list(list(self.cropobjects.values()), **kwargs)

    @Tracker(track_names=['output'],
             fn_name='model.export_cropobjects',
             tracker_name='model')
    def export_cropobjects(self, output, **kwargs):
        logging.info('Model: Exporting MungNodes to {0}'.format(output))
        with codecs.open(output, 'w', 'utf-8') as hdl:
            hdl.write(self.export_cropobjects_string(**kwargs))
            hdl.write('\n')

    @Tracker(track_names=[],
             fn_name='model.clear_cropobjects',
             tracker_name='model')
    def clear_cropobjects(self):
        logging.info('Model: Clearing all {0} cropobjects.'.format(len(self.cropobjects)))
        self.cropobjects = {}
        self.sync_cropobjects_to_graph()

    def clear_relationships(self, label=None, cropobjects=None):
        """Removes all relationships with the given label. If no label is given
        (default), removes all relationships."""
        if cropobjects is None:
            objids = [objid for objid in self.cropobjects]
        else:
            objids = [c.objid for c in cropobjects]

        if label is None:
            edges = list(self.graph.edges.keys())
        else:
            edges = [(from_objid, to_objid) for from_objid, to_objid in self.graph.edges
                     if (self.graph.edges[(from_objid, to_objid)] == label) and
                        ((from_objid in objids) or (to_objid in objids))]
        self.ensure_remove_edges(edges)


    def import_classes_definition(self, mlclasses):
        """Overwrites previous mlclasses definition -- there can only be
        one active at the same time.

        Note that this may invalidate all of the MungNodes in memory.

        Note that this also invalidates the current grammar.
        """
        self.mlclasses = {m.clsid: m for m in mlclasses}
        self.mlclasses_by_name = {m.name: m for m in mlclasses}

    def get_next_cropobject_id(self):
        if len(self.cropobjects) == 0:
            return 0
        return max(self.cropobjects.keys()) + 1

    ##########################################################################
    # Synchronizing with the graph.
    def sync_graph_to_cropobjects(self, cropobjects=None):
        """Ensures that the attachments are accurately reflected
        among the MungNodes. The attachments are build separately
        in the app, so they need to be written to the MungNodes
        explicitly.

        Edge label handling
        -------------------

        Edges labeled as ``Attachment`` in the graph get synced to
        the MungNode's inlinks and outlinks.

        Edges labeled as ``Precedence`` in the graph get synced
        to the MungNode's data, under the keys ``precedence_inlinks``
        and ``precedence_outlinks``, as lists of ints.

        .. warning::

            Clears all outlinks and inlinks from the MungNodes and replaces
            them with the graph's structure!

        :param cropobjects: A list of MungNodes which should be synced.
            If left to ``None``, will sync everything.
        """
        logging.debug('Model: Syncing {0} attachments to MungNodes.'
                       ''.format(len(self.graph.edges)))

        if cropobjects is None:
            cropobjects = list(self.cropobjects.values())

        for c in cropobjects:

            # Inlinks
            attachment_inlinks = self.graph.inlinks_of(c.objid, label='Attachment')
            c.inlinks = attachment_inlinks

            precedence_inlinks = self.graph.inlinks_of(c.objid, label='Precedence')
            if len(precedence_inlinks) > 0:
                c.data['precedence_inlinks'] = precedence_inlinks
            else:
                if 'precedence_inlinks' in c.data:
                    del c.data['precedence_inlinks']

            # Outlinks
            attachment_outlinks = self.graph.outlinks_of(c.objid,
                                                         label='Attachment')
            c.outlinks = attachment_outlinks

            precedence_outlinks = self.graph.outlinks_of(c.objid,
                                                         label='Precedence')
            if len(precedence_outlinks) > 0:
                c.data['precedence_outlinks'] = precedence_outlinks
            else:
                if 'precedence_outlinks' in c.data:
                    del c.data['precedence_outlinks']

    def sync_cropobjects_to_graph(self, cropobjects=None):
        """Ensures that the attachment structure in MungNodes
        is accurately reflected in the attachments data structure
        of the model. (Typically, you want to call this on importing
        a new set of MungNodes, to make sure their inlinks and outlinks
        are correctly represented in the attachment structures.

        .. warning::

            Clears the current graph and replaces it with the edges inferred
            from MungNodes!

        :param cropobjects: A list of MungNodes which should be synced.
            If left to ``None``, will sync everything.
        """
        if cropobjects is None:
            cropobjects = list(self.cropobjects.values())
            self.graph.clear()
        else:
            for c in cropobjects:
                self.graph.remove_obj_from_graph(c.objid)

        attachment_edges = []
        precedence_edges = []

        for c in cropobjects:
            self.graph.add_vertex(c.objid)
            # It is sufficient to collect outlinks -- the corresponding
            # inlink would just duplicate the edge.
            for o in c.outlinks:
                if c.objid != o:
                    attachment_edges.append((c.objid, o))
            if 'precedence_outlinks' in c.data:
                for o in c.data['precedence_outlinks']:
                    if c.objid != o:
                        precedence_edges.append((c.objid, o))

        # Add all edges at once.
        self.graph.add_edges(attachment_edges, label='Attachment')
        self.graph.add_edges(precedence_edges, label='Precedence')

    def ensure_consistent(self):
        """Make sure that the model is in a consistent state.
        (Fires all lazy synchronization routines between model components.)"""
        # self.ensure_cropobjects_consistent()
        self.ensure_no_loops()
        self.sync_graph_to_cropobjects()

    def ensure_cropobjects_consistent(self, cropobjects=None):
        """Makes sure that the MungNodes are all well-formed.
        Checks for:

        * Match between objid and uid

        Dispatches ``on_cropobjects`` in order to reflect the in-place
        updates.
        """
        if cropobjects is None:
            cropobjects = list(self.cropobjects.values())
        for c in cropobjects:
            dataset, doc, num = c._parse_uid(c.uid)
            if c.objid != num:
                logging.warn('MungNode consistency check: object with objid {0}'
                             ' has UID {1}, setting UID to match objid.'
                             ''.format(c.objid, c.uid))
                c.set_objid(c.objid)
        return cropobjects

    def ensure_no_loops(self):
        """Makes sure that there are no loops in the graph.
        This is especially important for precedence edges."""
        to_remove = []
        for a1, a2 in self.graph.edges:
            if a1 == a2:
                if (a2, a1) not in to_remove:
                    to_remove.append((a1, a2))
        for a1, a2 in to_remove:
            self.graph.ensure_remove_edge(a1, a2)
        self.sync_graph_to_cropobjects()

    def ensure_remove_edge(self, from_objid, to_objid):
        """Make sure that the given edge is not in the model.
        If it was there, it gets removed; otherwise, no action is taken.
        As opposed to this operation on the graph, on the model, the
        MungNodes in question have their inlink/outlink arrays
        updated as well.
        """
        self.graph.ensure_remove_edge(from_objid, to_objid)
        self.sync_graph_to_cropobjects(cropobjects=[self.cropobjects[from_objid],
                                                    self.cropobjects[to_objid]])

    def ensure_remove_edges(self, edges):
        _affected_cropobjects = []
        for from_objid, to_objid in edges:
            self.graph.ensure_remove_edge(from_objid, to_objid)
            _affected_cropobjects.append(self.cropobjects[from_objid])
            _affected_cropobjects.append(self.cropobjects[to_objid])
        self.sync_graph_to_cropobjects(cropobjects=_affected_cropobjects)

    def ensure_add_edge(self, edge, label='Attachment'):
        self.graph.ensure_add_edge(edge, label=label)
        self.sync_graph_to_cropobjects(cropobjects=[self.cropobjects[edge[0]],
                                                    self.cropobjects[edge[1]]])

    def ensure_add_edges(self, edges, label='Attachment'):
        self.graph.ensure_add_edges(edges=edges, label=label)
        _affected_objids = set(itertools.chain(*edges))
        _affected_cropobjects = [self.cropobjects[i] for i in _affected_objids]
        self.sync_graph_to_cropobjects(cropobjects=_affected_cropobjects)

    ##########################################################################
    # Integrity
    def validate_cropobjects(self):
        """Check that all current MungNode correspond to a class."""
        if len(self.mlclasses) == 0:
            raise ValueError('Cannot validate cropobjects without mlclasses.')
        if self.image is None:
            raise ValueError('Cannot validate cropobjects without image')
        shape = self.image.shape

        invalid_clsname_objs = []
        oversized_objs = []
        for c in list(self.cropobjects.values()):
            clsname = c.clsname
            if clsname not in self.mlclasses_by_name:
                invalid_clsname_objs.append(c)
            if c.top < 0 or c.left < 0:
                oversized_objs.append(c)
            if c.bottom > shape[0] or c.right > shape[1]:
                oversized_objs.append(c)

        if len(invalid_clsname_objs) > 0:
            return False
        if len(oversized_objs) > 0:
            return False
        return True

    def find_grammar_errors(self):
        vertices = {v: self.cropobjects[v].clsname for v in self.graph.vertices}
        edges = [e for e in list(self.graph.edges.keys())
                 if self.graph.edges[e] == 'Attachment']
        v, i, o, r_v, r_i, r_o = self.grammar.find_invalid_in_graph(vertices, edges,
                                                                    provide_reasons=True)
        return v, i, o, r_v, r_i, r_o

    def find_very_small_objects(self, bbox_threshold=10, mask_threshold=10):
        """Finds MungNodes that are very small.

        "Very small" means that their bounding box area is
        smaller than the given threshold or they consist of less
        than ``mask_threshold`` pixels."""
        very_small_cropobjects = []

        for c in list(self.cropobjects.values()):
            total_masked_area = c.mask.sum()
            total_bbox_area = c.width * c.height
            if total_bbox_area < bbox_threshold:
                very_small_cropobjects.append(c)
            elif total_masked_area < mask_threshold:
                very_small_cropobjects.append(c)

        return list(set([c.objid for c in very_small_cropobjects]))

    def find_vertices_with_loops(self):
        loop_objids = []
        for objid in self.cropobjects:
            if (objid, objid) in self.graph.edges:
                loop_objids.append(objid)
        return loop_objids

    def find_wrong_vertices(self, provide_reasons=False):
        v, i, o, r_v, r_i, r_o = self.find_grammar_errors()

        v_small = self.find_very_small_objects()
        # Merge with small objects.
        for objid in v_small:
            if objid not in v:
                v.append(objid)
                r_v[objid] = 'Object {0} is suspiciously small.'.format(objid)

        v_loops = self.find_vertices_with_loops()
        for objid in v_loops:
            if objid not in v:
                v.append(objid)
                r_v[objid] = 'Object {0} has loops.'.format(objid)

        if provide_reasons:
            return v, r_v
        return v

    def find_wrong_edges(self, provide_reasons=False):
        edges = [e for e in list(self.graph.edges.keys())
                 if self.graph.edges[e] == 'Attachment']

        v, i, o, r_v, r_i, r_o = self.find_grammar_errors()
        incoherent_beam_pairs = find_beams_incoherent_with_stems(list(self.cropobjects.values()))
        # Switching off misdirected ledger lines: there is something wrong with them
        misdirected_ledger_lines = find_misdirected_ledger_line_edges(list(self.cropobjects.values()))

        wrong_edges = [(n.objid, b.objid)
                       for n, b in incoherent_beam_pairs + misdirected_ledger_lines]

        disallowed_symbol_class_pairs = [(f, t) for f, t in edges
                                         if not self.grammar.validate_edge(self.cropobjects[f].clsname,
                                                                           self.cropobjects[t].clsname)]
        wrong_edges += disallowed_symbol_class_pairs
        return wrong_edges

    def find_related_staffs(self, cropobjects, with_stafflines=True):
        """Find all staffs that are related to any of the cropobjects
        in question. Ignores whether these staffs are already within
        the list of ``cropobjects`` passed to the function.

        Wraps the ``mung.graph.find_related_staffs()`` function.

        :param with_stafflines: If set, will also return all stafflines
            and staffspaces related to the discovered staffs.
        """
        related_staffs = find_related_staffs(cropobjects,
                                             list(self.cropobjects.values()),
                                             with_stafflines=with_stafflines)
        return related_staffs

    ##########################################################################
    # Keeping the model in a consistent state
    def on_grammar(self, instance, g):
        if g is None:
            return
        if self.parser is None:
            self.init_parser(grammar=g)
        else:
            self.parser.set_grammar(g)

    def on_mlclasses(self, instance, mlclasses):
        # Invalidate grammar and parser
        logging.warn('Model: MLClasses changed, invalidating grammar & parser!')
        self.parser = None
        self.grammar = None
        logging.warn('Model: MLClasses changed, invalidating objgraph!')
        self.graph.clear()

    ##########################################################################
    # Connected components: a useful thing to keep track of
    def _compute_cc_cache(self):
        logging.info('AnnotModel: Computing connected components...')
        cc, labels, bboxes = compute_connected_components(self.image)
        logging.info('AnnotModel: Got cc: {0}, labels: {1}, bboxes: {2}'
                     ''.format(cc, labels.shape, len(bboxes)))
        self._cc, self._labels, self._bboxes = cc, labels, bboxes
        logging.info('AnnotModel: ...done, there are {0} labels.'.format(cc))

    def _invalidate_cc_cache(self):
        self._cc = -1
        self._labels = None
        self._bboxes = None

    def _ensure_cc_cache(self):
        if self._cc_cache_is_empty:
            self._compute_cc_cache()

    @property
    def _cc_cache_is_empty(self):
        return self._cc < 0

    @property
    def cc(self):
        self._ensure_cc_cache()
        return self._cc

    @property
    def labels(self):
        self._ensure_cc_cache()
        return self._labels

    @property
    def bboxes(self):
        self._ensure_cc_cache()
        return self._bboxes
        # def plot_annotations(self):
        #     """Plot the current animation using Matplotlib."""
        #     rgb_img = cv2.cvtColor(self.image, cv2.COLOR_GRAY2RGB)
        #     annot_img = muscimarker_io.render_annotations(rgb_img,
        #                                                   self.cropobjects.values(),
        #                                                   self.mlclasses.values())
        #
        #     logging.info('Plotting annotation, image shape: {0}'.format(annot_img.shape))
        #     plt.imshow(annot_img)
        #     plt.show()


    ##########################################################################
    # Image manipulation
    def rotate_image_left(self):
        self.image = numpy.rot90(self.image)

    def rotate_image_right(self):
        self.image = numpy.rot90(self.image)

    ##########################################################################
    # Object detection interface
    def call_object_detection(self, bounding_box=None, margin=32,
                              clsnames=None):
        """Call object detection through ``self._object_detection_client``.

        Some "improvements" (quick workarounds):

        * A slightly larger bounding box is sent for detection. After receiving
          objects, those that are located at least partly in the margins are
          discarded. This helps with boundary artifacts. The size of the margin
          should roughly correspond to the size of the receptive field of an output
          pixel.

        :param clsnames: If set to None, will use current class. (In MUSCIMarker,
            this is configurable through ObjectDetectionTool settings: config
            class
        """
        if bounding_box is None:
            bounding_box = (0, 0, self.image.shape[0], self.image.shape[1])

        t, l, b, r = bounding_box
        if ((b - t) == 0) or ((r - l) == 0):
            logging.info('Object detection: Attempted detection with empty'
                         ' bounding box: {0}'.format(bounding_box))
            return

        # Apply margin
        _t = max(0, t - margin)
        _l = max(0, l - margin)
        _b = min(self.image.shape[0], b + margin)
        _r = min(self.image.shape[1], r + margin)

        real_margin = t - _t, l - _l, _b - b, _r - r

        self._object_detection_client.input_bounding_box = bounding_box
        self._object_detection_client.input_bounding_box_margin = real_margin

        image_crop = self.image[_t:_b, _l:_r]

        if clsnames is None:
            clsnames = [App.get_running_app().currently_selected_mlclass_name]
        if len(clsnames) == 0:
            logging.warning('Object detection: got called without specifying'
                            ' clsname and without specifying that the current'
                            ' clsname should be used.')
            return

        request = {'image': image_crop,
                   'clsname': clsnames,
                   }
        self._object_detection_client.input = request


    def process_detection_result(self, instance, pos):
        """Incorporates the detection result into the model.

        The detection result arrives as a list of MungNodes.
        The model has to make sure their ``objid`` and potentially
        ``doc`` attributes are valid. Docname is handled on export,
        so it is not a problem here, but the objids of detection
        results start at 0, so they must be corrected.

        Then, the model needs to shift the MungNodes bottom and right
        according to the bounding box of the detection input region.

        After ensuring the MungNodes can be added to the model
        without introducing conflicts,
        """
        result_cropobjects = pos
        logging.info('Got a total of {0} detected MungNodes.'
                     ''.format(len(result_cropobjects)))

        processed_cropobjects = self._detection_filter_tiny(result_cropobjects)
        processed_cropobjects = self._detection_filter_contained(result_cropobjects)
        processed_cropobjects = self._detection_apply_objids(processed_cropobjects)
        processed_cropobjects = self._detection_apply_shift(processed_cropobjects)
        processed_cropobjects = self._detection_apply_margin(processed_cropobjects,
                                                             margin=self._object_detection_client.input_bounding_box_margin,
                                                             bounding_box=self._object_detection_client.input_bounding_box)

        # Do false positive filtering here (per class)

        for c in processed_cropobjects:
            self.add_cropobject(c)

    def _detection_apply_margin(self, cropobjects, margin, bounding_box):
        """Checks if the MungNode aren't within the given margin. Note that this
        is applied *after* translation back to coordinates w.r.t. image, not w.r.t.
        detection crop; the bounding box is therefore also w.r.t. image.

        Because the bounding box is recorded *without* the margin, we do not explicitly need
        it here. We just need to check that all the detected objects fit inside this
        bounding box.
        """
        if margin is None:
            return cropobjects

        if bounding_box is None:
            logging.warn('Trying to filter boundary artifacts, but no input bounding box available...')
            return cropobjects

        def _within_margin(c, m, bbox):
            t, l, b, r = bbox
            # mt, ml, mb, mr = m
            if (c.top < t) \
                or (c.left < l) \
                or (c.bottom > b) \
                or (c.right > r):
                return False
            else:
                return True

        output_cropobjects = [c for c in cropobjects if _within_margin(c, margin, bounding_box)]
        cropobjects_in_margin = [c for c in cropobjects if c not in output_cropobjects]
        logging.info('Detection: Bounding box: {0}'.format(bounding_box))
        logging.info('Detection: Margin: {0}'.format(margin))
        logging.info('Detection: Filtering out {0} cropobjects found only in the margin.'
                     ''.format(len(cropobjects_in_margin)))
        for c in cropobjects_in_margin:
            logging.info('Detection: \tC. in margin: bbox {0}'.format(c.bounding_box))

        return output_cropobjects

    def _detection_apply_shift(self, cropobjects):
        it, il, ib, ir = self._object_detection_client.input_bounding_box
        mt, ml, mb, mr = self._object_detection_client.input_bounding_box_margin
        for c in cropobjects:
            c.translate(down=it - mt, right=il - ml)
        return cropobjects

    def _detection_apply_objids(self, cropobjects):
        _delta_objid = self.get_next_cropobject_id()
        _next_objid = _delta_objid

        output_cropobjects = []
        for c in cropobjects:
            c.set_objid(_next_objid)

            c.inlinks = [i + _delta_objid for i in c.inlinks]
            c.outlinks = [o + _delta_objid for o in c.outlinks]

            output_cropobjects.append(c)
            _next_objid += 1

        return output_cropobjects

    def _detection_filter_tiny(self, cropobjects, min_mask_area=40, min_size=5):
        """Exceptional treatment:

        * Stafflines: only checks width
        * Duration dots: special mask sum (only 10)

        :param cropobjects:
        :param min_mask_area:
        :param min_size:
        :return:
        """
        # Note that stafflines get special treatment: only checked against width, not height.
        tiny = [c for c in cropobjects if c.mask.sum() < min_mask_area]
        logging.info('Detection: Filtering out {0} tiny cropobjects'.format(len(tiny)))
        narrow = [c for c in cropobjects if c.width < min_size]
        logging.info('Detection: Filtering out {0} narrow cropobjects'.format(len(narrow)))

        output_stafflines = [c for c in cropobjects
                             if (c.clsname == _CONST.STAFFLINE_CLSNAME) and (c.width >= min_size)]
        duration_dots = [c for c in cropobjects
                         if (c.clsname == 'duration-dot') \
                            and (c.mask.sum() >= 10)]
        output = [c for c in cropobjects
                  if (c.clsname != _CONST.STAFFLINE_CLSNAME) \
                    and (c.clsname != 'duration-dot')
                    and (c.mask.sum() >= min_mask_area) \
                    and (min(c.width, c.height) >= min_size)]

        return output + output_stafflines + duration_dots

    def _detection_filter_contained(self, cropobjects):
        """Filters out cropobjects that are fully within another object's bounding
        box, have a Dice of at least 0.95 with the containing object, and are
        smaller than 0.9 of the container object area.

        Does *not* consider key signatures, time signatures, measure separators.
        """
        _cdict = {c.objid: c for c in cropobjects}

        return cropobjects

    ##########################################################################
    # Staffline building
    def process_stafflines(self,
                           build_staffs=False,
                           build_staffspaces=False,
                           add_staff_relationships=False):
        """Merges staffline fragments into stafflines. Can group them into staffs,
        add staffspaces, and add the various obligatory relationships of other
        objects to the staff objects. Required before attempting to export MIDI."""
        if len([c for c in list(self.cropobjects.values()) if c.clsname == 'staff']) > 0:
            logging.warn('Some stafflines have already been processed. Reprocessing'
                         ' is not certain to work.')
            # return

        try:
            new_cropobjects = mung.stafflines.merge_staffline_segments(list(self.cropobjects.values()))
        except ValueError as e:
            logging.warning('Model: Staffline merge failed:\n\t\t'
                            '{0}'.format(e))
            return

        try:
            if build_staffs:
                staffs = mung.stafflines.build_staff_cropobjects(new_cropobjects)
                new_cropobjects = new_cropobjects + staffs
        except Exception as e:
            logging.warning('Building staffline cropobjects from merged segments failed:'
                            ' {0}'.format(e))
            return

        try:
            if build_staffspaces:
                staffspaces = mung.stafflines.build_staffspace_cropobjects(new_cropobjects)
                new_cropobjects = new_cropobjects + staffspaces
        except Exception as e:
            logging.warning('Building staffspace cropobjects from stafflines failed:'
                            ' {0}'.format(e))
            return

        try:
            if add_staff_relationships:
                new_cropobjects = mung.stafflines.add_staff_relationships(new_cropobjects)
        except Exception as e:
            logging.warning('Adding staff relationships failed:'
                            ' {0}'.format(e))
            return

        self.import_cropobjects(new_cropobjects)

    ##########################################################################
    # MIDI export
    def build_midi(self, selected_cropobjects=None,
                   retain_pitches=True,
                   retain_durations=True,
                   retain_onsets=True):
        """Attempts to export a MIDI file from the current graph. Assumes that
        all the staff objects and their relations have been correctly established,
        and that the correct precedence graph is available.

        :param retain_pitches: If set, will record the pitch information
            in pitched objects.

        :param retain_durations: If set, will record the duration information
            in objects to which it applies.

        :returns: A single-track ``midiutil.MidiFile.MIDIFile`` object. It can be
            written to a stream using its ``mf.writeFile()`` method."""
        pitch_inference_engine = PitchInferenceEngine()
        time_inference_engine = OnsetsInferenceEngine(cropobjects=list(self.cropobjects.values()))

        try:
            logging.info('Running pitch inference.')
            pitches, pitch_names = pitch_inference_engine.infer_pitches(list(self.cropobjects.values()),
                                                                        with_names=True)
        except Exception as e:
            logging.warning('Model: Pitch inference failed!')
            logging.exception(traceback.format_exc(e))
            return

        if retain_pitches:
            for objid in pitches:
                c = self.cropobjects[objid]
                pitch_step, pitch_octave = pitch_names[objid]
                c.data['midi_pitch_code'] = pitches[objid]
                c.data['normalized_pitch_step'] = pitch_step
                c.data['pitch_octave'] = pitch_octave

        try:
            logging.info('Running durations inference.')
            durations = time_inference_engine.durations(list(self.cropobjects.values()))
        except Exception as e:
            logging.warning('Model: Duration inference failed!')
            logging.exception(traceback.format_exc(e))
            return

        if retain_durations:
            for objid in durations:
                c = self.cropobjects[objid]
                c.data['duration_beats'] = durations[objid]

        try:
            logging.info('Running onsets inference.')
            onsets = time_inference_engine.onsets(list(self.cropobjects.values()))
        except Exception as e:
            logging.warning('Model: Onset inference failed!')
            logging.exception(traceback.format_exc(e))
            return

        if retain_onsets:
            for objid in onsets:
                c = self.cropobjects[objid]
                c.data['onset_beats'] = onsets[objid]

        # Process ties
        durations, onsets = time_inference_engine.process_ties(list(self.cropobjects.values()),
                                                               durations, onsets)

        tempo = int(App.get_running_app().config.get('midi', 'default_tempo'))

        if selected_cropobjects is None:
            selected_cropobjects = list(self.cropobjects.values())
        selection_objids = [c.objid for c in selected_cropobjects]

        midi_builder = MIDIBuilder()
        mf = midi_builder.build_midi(
            pitches=pitches, durations=durations, onsets=onsets,
            selection=selection_objids, tempo=tempo)

        return mf

    def infer_midi(self, cropobjects=None, play=True):
        """Attempts to play the midi file."""
        if not cropobjects:
            cropobjects = list(self.cropobjects.values())

        soundfont = App.get_running_app().config.get('midi', 'soundfont')

        midi = self.build_midi(selected_cropobjects=cropobjects)
        if play and (midi is not None):
            play_midi(midi=midi,
                      tmp_dir=App.get_running_app().tmp_dir,
                      soundfont=soundfont)
        else:
            logging.warning('Exporting MIDI failed, nothing to play!')

    def clear_midi_information(self):
        """Removes all the information from all MungNodes."""
        for c in list(self.cropobjects.values()):
            if c.data is None:
                continue
            if 'midi_pitch_code' in c.data:
                del c.data['midi_pitch_code']
            if 'normalized_pitch_step' in c.data:
                del c.data['normalized_pitch_step']
            if 'pitch_octave' in c.data:
                del c.data['pitch_octave']
            if 'duration_beats' in c.data:
                del c.data['duration_beats']
            if 'onset_beats' in c.data:
                del c.data['onset_beats']
