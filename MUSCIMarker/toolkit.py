"""This module implements a class that..."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function, unicode_literals

import collections
import copy
import logging
import time
from builtins import range
from builtins import zip

import numpy
from kivy.app import App
from kivy.core.window import Window
from kivy.properties import ObjectProperty, BooleanProperty, ListProperty, NumericProperty
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from mung.node import split_cropobject_on_connected_components
from mung.inference.constants import InferenceEngineConstants as _CONST
from past.utils import old_div
from skimage.draw import polygon, line
from skimage.filters import threshold_otsu

from MUSCIMarker.editor import BoundingBoxTracer, ConnectedComponentBoundingBoxTracer, TrimmedBoundingBoxTracer, \
    LineTracer
from MUSCIMarker.utils import bbox_to_integer_bounds, image_mask_overlaps_cropobject, image_mask_overlaps_model_edge, \
    bbox_intersection

__version__ = "0.0.1"
__author__ = "Jan Hajic jr."


class MUSCIMarkerTool(Widget):
    """A MUSCIMarkerTool defines a set of available actions.
    For instance the viewing tool enables the user to freely scale and move
    the image around; the selection tool provides a click & drag bounding box drawing
    interface to create new MungNodes, etc.

    The tools define a set of Widgets that get added to the editor Layout, and a set
    of shortcuts that are made available through the Command Palette.
    [TODO] A third part of the tool definition is a set of keyboard shortcuts.
    This defines the possible interactions while a tool is active.

    During initialization, the new tool retains a reference to the MUSCIMarkerApp
    that created it. This way, it can translate user actions into model operations:
    e.g. the ManualSelectTool can call an "add MungNode" controller method.
    """

    def __init__(self, app, editor_widget, command_widget, **kwargs):
        super(MUSCIMarkerTool, self).__init__(**kwargs)

        self.editor_widget_ref = editor_widget
        self.command_palette_ref = command_widget
        self.app_ref = app

        self.editor_widgets = self.create_editor_widgets()
        self.command_palette_widgets = self.create_command_widgets()
        self.keyboard_shortcuts = self.create_keyboard_shortcuts()

        Window.bind(on_key_down=self.on_key_down)
        Window.bind(on_key_up=self.on_key_up)

    def init_editor_widgets(self):
        for w in list(self.editor_widgets.values()):
            self.editor_widget_ref.add_widget(w)

    def init_command_palette(self):
        for c in list(self.command_palette_widgets.values()):
            self.command_palette_ref.add_widget(c)

    def init_keyboard_shortcuts(self):
        for k, action in self.keyboard_shortcuts.items():
            self.app_ref.keyboard_dispatch[k] = action

    def deactivate(self):
        for w in list(self.editor_widgets.values()):
            self.editor_widget_ref.remove_widget(w)
        for c in list(self.command_palette_widgets.values()):
            self.command_palette_ref.remove_widget(c)

        for k in self.keyboard_shortcuts:
            del self.app_ref.keyboard_dispatch[k]

    # Override these two to make the tool do something.
    def create_editor_widgets(self):
        return collections.OrderedDict()

    def create_command_widgets(self):
        return collections.OrderedDict()

    def create_keyboard_shortcuts(self):
        return collections.OrderedDict()

    def on_key_down(self, window, key, scancode, codepoint, modifier):
        # logging.info('ToolKeyboard: Down {0}'.format((key, scancode, codepoint, modifier)))
        # return True
        pass

    def on_key_up(self, window, key, scancode, *args, **kwargs):
        # logging.info('ToolKeyboard: Up {0}'.format((key, scancode)))
        # return True
        pass

    def model_to_editor_bbox(self, m_t, m_l, m_b, m_r):
        """Use this method to convert a bounding box in the model
        world to the editor world."""
        ed_t, ed_l, ed_b, ed_r = self.app_ref.image_scaler.bbox_model2widget(m_t, m_l, m_b, m_r)
        return ed_t, ed_l, ed_b, ed_r

    def editor_to_model_bbox(self, ed_t, ed_l, ed_b, ed_r):
        """Use this method to convert a bounding box in the editor
        world to the model world."""
        m_t, m_l, m_b, m_r = self.app_ref.image_scaler.bbox_widget2model(ed_t, ed_l, ed_b, ed_r)
        return m_t, m_l, m_b, m_r

    def editor_to_model_points(self, points):
        """Converts a list of points such as from a LineTracer into a list
        of (x, y) points in the model world."""
        point_set_as_tuples = [p for i, p in enumerate(zip(points[:-1], points[1:]))
                               if i % 2 == 0]
        m_points = [self.app_ref.image_scaler.point_widget2model(wX, wY)
                    for wX, wY in point_set_as_tuples]
        m_points = [(int(x), int(y)) for x, y in m_points]

        # Let's deal with points on the boundary or outside
        m_points_x, m_points_y = list(zip(*m_points))
        m_points_x = [max(0, min(x, self.app_ref.image_scaler.model_height - 1))
                      for x in m_points_x]
        m_points_y = [max(0, min(y, self.app_ref.image_scaler.model_width - 1))
                      for y in m_points_y]
        m_points = list(zip(m_points_x, m_points_y))

        return m_points

    def model_mask_from_points(self, m_points):
        _t_start = time.clock()

        mask = numpy.zeros(self._model_image.shape, dtype='uint8')

        _t_mask_creation = time.clock()

        # Possible speedup:
        m_points_x, m_points_y = list(zip(*m_points))
        chi = polygon(m_points_x, m_points_y)

        _t_polygon = time.clock()

        mask[chi] = 1.0

        _t_mask_application = time.clock()

        logging.info('Toolkit.model_mask_from_points: {0} pts, area {1},'
                     'polygon(): {2:.5f}'
                     ''.format(len(m_points),
                               len(chi[0]),
                               _t_polygon - _t_mask_creation,
                               _t_mask_application - _t_polygon))
        return mask

    @property
    def _model(self):
        return self.app_ref.annot_model

    @property
    def _model_image(self):
        return self._model.image


###############################################################################


class ViewingTool(MUSCIMarkerTool):
    pass


###############################################################################


class AddSymbolTool(MUSCIMarkerTool):
    current_cropobject_selection = ObjectProperty(None)
    current_cropobject_model_selection = ObjectProperty(None)
    current_cropobject_mask = ObjectProperty(None)

    automask = BooleanProperty(True)

    def create_editor_widgets(self):
        editor_widgets = collections.OrderedDict()
        editor_widgets['bbox_tracer'] = BoundingBoxTracer()
        editor_widgets['bbox_tracer'].bind(
            current_finished_bbox=self.current_selection_and_mask_from_bbox_tracer)
        return editor_widgets

    def create_command_widgets(self):
        command_widgets = collections.OrderedDict()
        c = Button(
            size_hint=(1.0, 0.1),
            text='Clear bboxes',
            on_release=self.editor_widgets['bbox_tracer'].clear
        )
        command_widgets['clear'] = c
        return command_widgets

    def on_current_cropobject_selection(self, instance, pos):
        # Ask the app to build MungNode from the bbox.
        logging.info('ManualSelectTool: fired on_current_cropobject_selection with pos={0}'
                     ''.format(pos))
        self.app_ref.add_cropobject_from_selection(
            self.current_cropobject_selection,
            mask=self.current_cropobject_mask)

        # Automatically clears the bounding box (it gets rendered as the new symbol
        # gets recorded).
        self.editor_widgets['bbox_tracer'].clear()

    def on_current_cropobject_model_selection(self, instance, pos):
        # Ask the app to build MungNode from the bbox.
        logging.info('AddSymbolTool: fired on_current_cropobject_model_selection with pos={0}'
                     ''.format(pos))
        self.app_ref.add_cropobject_from_model_selection(
            self.current_cropobject_model_selection,
            mask=self.current_cropobject_mask)

        # Automatically clears the bounding box (it gets rendered as the new symbol
        # gets recorded).
        self.editor_widgets['bbox_tracer'].clear()

    def current_selection_from_bbox_tracer(self, instance, pos):
        logging.info('ManualSelectTool: fired current_selection_from_bbox_tracer with pos={0}'
                     ''.format(pos))
        self.current_cropobject_selection = pos

    def current_selection_and_mask_from_bbox_tracer(self, instance, pos):
        # Clear the last mask
        # self.current_cropobject_mask = None
        # ...should not be necessary

        # Get mask
        ed_t, ed_l, ed_b, ed_r = pos['top'], pos['left'], \
                                 pos['bottom'], pos['right']
        m_t, m_l, m_b, m_r = self.editor_to_model_bbox(ed_t, ed_l, ed_b, ed_r)
        m_t, m_l, m_b, m_r = bbox_to_integer_bounds(m_t, m_l, m_b, m_r)

        image = self.app_ref.annot_model.image

        crop = image[m_t:m_b, m_l:m_r]
        mask = numpy.ones(crop.shape, dtype='uint8')
        mask *= crop
        mask[mask != 0] = 1

        self.current_cropobject_mask = mask

        # Now create current selection
        self.current_cropobject_model_selection = {'top': m_t,
                                                   'left': m_l,
                                                   'bottom': m_b,
                                                   'right': m_r}
        # self.current_selection_from_bbox_tracer(instance=instance, pos=pos)


###############################################################################


class ConnectedSelectTool(AddSymbolTool):
    current_cropobject_selection = ObjectProperty(None)

    # Caches.
    _cc = NumericProperty(-1)
    _labels = ObjectProperty(None)
    _bboxes = ObjectProperty(None)

    def create_editor_widgets(self):
        editor_widgets = collections.OrderedDict()
        editor_widgets['bbox_tracer'] = BoundingBoxTracer()
        editor_widgets['bbox_tracer'].bind(current_finished_bbox=self.current_selection_and_mask_from_bbox_tracer)
        return editor_widgets

    def current_selection_and_mask_from_bbox_tracer(self, instance, pos):

        # Clear the last mask
        # self.current_cropobject_mask = None
        # ...should not be necessary

        # Get mask
        ed_t, ed_l, ed_b, ed_r = pos['top'], pos['left'], \
                                 pos['bottom'], pos['right']

        m_t, m_l, m_b, m_r = self.editor_to_model_bbox(ed_t, ed_l, ed_b, ed_r)
        m_t, m_l, m_b, m_r = bbox_to_integer_bounds(m_t, m_l, m_b, m_r)

        # Processing a single click: converting to single-pixel bbox
        if (m_t == m_b) and (m_l == m_r):
            m_t = int(m_t)
            m_b = int(m_b) + 1
            m_l = int(m_l)
            m_r = int(m_r) + 1

        mask, cc_bbox = self.cc_model_mask_and_bbox_from_model_bbox(m_t, m_l, m_b, m_r)

        if mask is None:
            logging.info('CCSelect: no mask')
            return

        self.current_cropobject_mask = mask

        # Now create current selection
        cc_t, cc_l, cc_b, cc_r = cc_bbox
        self.current_cropobject_model_selection = {'top': cc_t,
                                                   'left': cc_l,
                                                   'bottom': cc_b,
                                                   'right': cc_r}
        # self.current_selection_from_bbox_tracer(instance=instance, pos=pos)

    def cc_model_mask_and_bbox_from_model_bbox(self, t, l, b, r):
        """The "clever" part of the CC tracking."""
        logging.info('CCselect: getting mask and new bounding box from labels.')

        self._cc = self._model.cc
        self._labels = self._model.labels
        self._bboxes = self._model.bboxes

        selected_labels = set([l for l in self._labels[t:b, l:r].flatten()
                               if l != 0])  # Ignore background
        # Nothing selected
        if len(selected_labels) == 0:
            logging.warn('CCselect: no cc selected!')
            return None, None

        logging.info('CCSelect: got labels {0}'.format(selected_labels))

        selected_bboxes = numpy.array([self._bboxes[l] for l in selected_labels])

        # Get the combined bbox
        cc_t = min(selected_bboxes[:, 0])
        cc_l = min(selected_bboxes[:, 1])
        cc_b = max(selected_bboxes[:, 2])
        cc_r = max(selected_bboxes[:, 3])

        # Mask:
        #   - crop the labels to this box
        lcrop = self._labels[cc_t:cc_b, cc_l:cc_r]

        #   - create the zeros
        mask = numpy.zeros(lcrop.shape, dtype='uint8')

        #   - mark as 1 all pixels that have one of the selected labels
        #     in the crop
        for l in selected_labels:
            logging.info('CCSelect: running mask against label {0}'.format(l))
            mask[lcrop == l] = 1

        return mask, (cc_t, cc_l, cc_b, cc_r)


###############################################################################


class AverageSymbolTool(AddSymbolTool):
    """This tool uses the average bounding box and mask
    for a given symbol, computed from all the instances
    of the given symbol class that are in the current
    annotation.

    Operates on click, or click & drag: on release, will
    create the symbol centered around the point where you let go.
    """
    _current_bbox_size = -1, -1
    _current_mask = None

    def compute_average_bbox(self, clsname):
        cropobjects = [c for c in self._model.cropobjects.values()
                       if c.clsname == clsname]
        hs = [c.height for c in cropobjects]
        h_avg = numpy.mean(hs)
        ws = [c.width for c in cropobjects]
        w_avg = numpy.mean(ws)
        return int(numpy.round(h_avg)) + 1, int(numpy.round(w_avg)) + 1

    def set_average_bbox(self, clsname):
        self._current_bbox_size = self.compute_average_bbox(clsname)

    def set_average_mask(self):
        if min(self._current_bbox_size) < 0:
            self._current_mask = None
            logging.warning('AverageSymbolTool: Cannot set mask'
                            ' when no symbol class is selected!')
            return
        self._current_mask = numpy.ones(self._current_bbox_size,
                                        dtype='uint8')

    def set_to_current_class(self):
        clsname = self.app_ref.currently_selected_mlclass_name
        self.set_average_bbox(clsname)
        self.set_average_mask()

    def create_command_widgets(self):
        return collections.OrderedDict()

    def create_editor_widgets(self):
        self.set_to_current_class()
        editor_widgets = collections.OrderedDict()
        editor_widgets['bbox_tracer'] = LineTracer()
        editor_widgets['bbox_tracer'].bind(points=self.current_selection_and_mask_from_points)
        return editor_widgets

    def current_selection_and_mask_from_points(self, instance, pos):
        e_col, e_row = pos[-2], pos[-1]
        m_points = self.editor_to_model_points([e_col, e_row])
        m_row, m_col = m_points[0][0], m_points[0][1]
        h, w = self._current_bbox_size
        dh = h // 2
        dw = w // 2
        m_t = m_row - dh
        m_l = m_col - dw
        # Ensure shape despite integer division
        m_b = m_row + (dh + (2 * dh - h))
        m_r = m_col + (dw + (2 * dw - w))

        self.current_cropobject_mask = numpy.ones((m_b - m_t, m_r - m_l),
                                                  dtype='uint8')
        self.current_cropobject_model_selection = {'top': m_t,
                                                   'left': m_l,
                                                   'bottom': m_b,
                                                   'right': m_r}


###############################################################################


class TrimmedSelectTool(AddSymbolTool):
    current_cropobject_selection = ObjectProperty(None)

    def create_editor_widgets(self):
        editor_widgets = collections.OrderedDict()
        editor_widgets['bbox_tracer'] = TrimmedBoundingBoxTracer()
        editor_widgets['bbox_tracer'].bind(current_finished_bbox=self.current_selection_from_bbox_tracer)
        return editor_widgets


###############################################################################


class LassoBoundingBoxSelectTool(MUSCIMarkerTool):
    """Note: cannot currently deal with nonconvex areas. Use the trimmed lasso
    tool instead (TLasso).

    The Lasso selection tool allows to specify in freehand a region that should
    be assigned a label. All lasso tools assign a mask as well as a bounding
    box to the MungNode.

    Bounding box: editor vs. model
    -------------------------------

    There is an issue with repeated scaling because of rounding errors.
    Generally, once the model-world bbox is computed, it should propagate
    all the way to actually adding the MungNode.

    """
    current_cropobject_selection = ObjectProperty(None)
    current_cropobject_model_selection = ObjectProperty(None)
    current_cropobject_mask = ObjectProperty(None)

    do_helper_line = BooleanProperty(False)
    helper_line_min_length = NumericProperty(100)

    def __init__(self, app, editor_widget, command_widget,
                 do_helper_line=False, helper_line_min_length=100,
                 **kwargs):
        logging.info('Toolkit: Initializing Lasso tool with do_helper_line={0},'
                     'kwargs = {1}'.format(do_helper_line, kwargs))
        self.do_helper_line = do_helper_line
        self.helper_line_min_length = helper_line_min_length
        super(LassoBoundingBoxSelectTool, self).__init__(app=app,
                                                         editor_widget=editor_widget,
                                                         command_widget=command_widget,
                                                         **kwargs)

    def create_editor_widgets(self):
        editor_widgets = collections.OrderedDict()
        editor_widgets['line_tracer'] = LineTracer()
        editor_widgets['line_tracer'].do_helper_line = self.do_helper_line
        editor_widgets['line_tracer'].helper_line_threshold = self.helper_line_min_length
        editor_widgets['line_tracer'].bind(points=self.current_selection_and_mask_from_points)
        return editor_widgets

    def selection_from_points(self, points):
        """Returns editor coordinates, which means that bottom < top and the coords
        need to be vertically inverted."""
        point_set_as_tuples = [p for i, p in enumerate(zip(points[:-1], points[1:]))
                               if i % 2 == 0]
        # This is the Kivy --> numpy transposition
        p_horizontal, p_vertical = list(zip(*point_set_as_tuples))

        # Let's deal with points on the boundary or outside
        p_horizontal = [max(0, min(x, self.app_ref.image_scaler.widget_width - 1))
                        for x in p_horizontal]
        p_vertical = [max(0, min(y, self.app_ref.image_scaler.widget_height - 1))
                      for y in p_vertical]

        left = min(p_horizontal)
        right = max(p_horizontal)

        top = max(p_vertical)
        bottom = min(p_vertical)
        selection = {'top': top, 'left': left, 'bottom': bottom, 'right': right}

        return selection

    def model_selection_from_points(self, points):
        e_sel = self.selection_from_points(points)
        wT, wL, wB, wR = e_sel['top'], e_sel['left'], e_sel['bottom'], e_sel['right']
        mT, mL, mB, mR = self.app_ref.image_scaler.bbox_widget2model(wT, wL, wB, wR)
        return {'top': mT, 'left': mL, 'bottom': mB, 'right': mR}

    def mask_uncut_from_points(self, points):
        point_set_as_tuples = [p for i, p in enumerate(zip(points[:-1], points[1:]))
                               if i % 2 == 0]

        m_points = [self.app_ref.image_scaler.point_widget2model(wX, wY)
                    for wX, wY in point_set_as_tuples]

        m_points = [(int(x), int(y)) for x, y in m_points]
        mask = numpy.zeros((self.app_ref.image_scaler.model_height,
                            self.app_ref.image_scaler.model_width), dtype='uint8')
        m_points_x, m_points_y = list(zip(*m_points))

        # Let's deal with points on the boundary or outside
        m_points_x = [max(0, min(x, self.app_ref.image_scaler.model_height - 1))
                      for x in m_points_x]
        m_points_y = [max(0, min(y, self.app_ref.image_scaler.model_width - 1))
                      for y in m_points_y]

        chi = polygon(m_points_x, m_points_y)
        mask[chi] = 1.0

        return mask

    def cut_mask_to_selection(self, mask, selection):
        """Given a model-world uncut mask of the whole model image
        and an editor-world selection, cuts the mask to correspond
        to the given editor-world selection.

        Given an editor-world selection, however, the model-world
        coordinates may turn out to be non-integers. We need to mimic
        the model-world procedure for converting these to integers,
        to ensure that the mask's shape will exactly mimic the shape
        of the MungNode's integer bounding box.
        """
        wT, wL, wB, wR = selection['top'], selection['left'], selection['bottom'], selection['right']
        mT, mL, mB, mR = self.app_ref.image_scaler.bbox_widget2model(wT, wL, wB, wR)
        mT, mL, mB, mR = bbox_to_integer_bounds(mT, mL, mB, mR)
        logging.info('LassoBoundingBoxTool.cut_mask_to_selection: cutting to {0}, h={1}, w={2}'
                     ''.format((mT, mL, mB, mR), mB - mT, mR - mL))
        return mask[mT:mB, mL:mR]

    def cut_mask_to_model_selection(self, mask, selection):
        """Like cut_mask_to_selection, but operates on model-world selection."""
        mT, mL, mB, mR = selection['top'], selection['left'], selection['bottom'], selection['right']
        mT, mL, mB, mR = bbox_to_integer_bounds(mT, mL, mB, mR)
        logging.info('LassoBoundingBoxTool.cut_mask_to_model_selection: cutting to {0}, h={1}, w={2}'
                     ''.format((mT, mL, mB, mR), mB - mT, mR - mL))
        return mask[mT:mB, mL:mR]

    def restrict_mask_to_nonzero(self, mask):
        """Given a uncut mask, restricts it to be True only for nonzero pixels
        of the image. Modifies the input mask (doesn't copy)."""
        # TODO: This does not work properly! See AddSymbolTool.
        if mask is None:
            return None
        img = self.app_ref.annot_model.image
        mask[img == 0] = 0
        return mask

    # Not used
    def current_selection_from_points(self, instance, pos):
        selection = self.selection_from_points(pos)
        if selection is not None:
            self.current_cropobject_selection = selection

    # Not used
    def current_mask_from_points(self, instance, pos):
        """Computes the lasso mask in model coordinates."""
        mask_uncut = self.mask_uncut_from_points(pos)
        if self.app_ref.config.get('toolkit', 'cropobject_mask_nonzero_only'):
            mask_uncut = self.restrict_mask_to_nonzero(mask_uncut)
        if mask_uncut is not None:
            selection = self.selection_from_points(pos)
            mask = self.cut_mask_to_selection(mask_uncut, selection)
            self.current_cropobject_mask = mask

    # Used (bound when constructing editor widgets)
    def current_selection_and_mask_from_points(self, instance, pos):
        """Triggers adding a MungNode with both bbox and mask."""
        if pos is None:
            logging.info('LassoBoundingBoxSelect: No points, clearing & skipping.')
            self.editor_widgets['line_tracer'].clear()
            return

        # Returns None if it's not possible to create the mask.
        mask_uncut = self.mask_uncut_from_points(pos)
        if self.app_ref.config.get('toolkit', 'cropobject_mask_nonzero_only'):
            mask_uncut = self.restrict_mask_to_nonzero(mask_uncut)

        if mask_uncut is not None:
            # bbox: stay in the model world once computed & propagate
            model_selection = self.model_selection_from_points(pos)
            if model_selection is None:
                logging.info('LassoBoundingBoxSelect: model selection not generated,'
                             ' clearing & skipping')
                self.editor_widgets['line_tracer'].clear()
                pass
            else:
                logging.info('LassoBoundingBoxSelect: Got model_selection {0}'
                             ''.format(model_selection))
                mask = self.cut_mask_to_model_selection(mask_uncut, model_selection)
                logging.info('LassoBoundingBoxSelect: uncut mask shape {0},'
                             ' cut mask shape {1}'.format(mask_uncut.shape, mask.shape))
                self.current_cropobject_mask = mask
                logging.info('LassoBoundingBoxSelect: Recording model selection {0}'
                             ''.format(model_selection))
                self.current_cropobject_model_selection = model_selection

    def on_current_cropobject_selection(self, instance, pos):
        # Ask the app to build MungNode from the bbox.
        logging.info('LassoBoundingBoxSelect: fired on_current_cropobject_selection with pos={0}'
                     ''.format(pos))
        self.app_ref.add_cropobject_from_selection(self.current_cropobject_selection,
                                                   mask=self.current_cropobject_mask)

        # Automatically clears the bounding box (it gets rendered as the new symbol
        # gets recorded).
        self.editor_widgets['line_tracer'].clear()

    def on_current_cropobject_model_selection(self, instance, pos):
        # Ask the app to build MungNode from the bbox.
        logging.info('LassoBoundingBoxSelect: fired on_current_cropobject_model_selection with pos={0}'
                     ''.format(pos))
        self.app_ref.add_cropobject_from_model_selection(
            self.current_cropobject_model_selection,
            mask=self.current_cropobject_mask)

        # Automatically clears the bounding box (it gets rendered as the new symbol
        # gets recorded).
        self.editor_widgets['line_tracer'].clear()

    def model_to_editor_bbox(self, m_t, m_l, m_b, m_r):
        """Use this method to convert the bounding box in the model
        world to the editor world."""
        ed_t, ed_l, ed_b, ed_r = self.app_ref.image_scaler.bbox_model2widget(m_t, m_l, m_b, m_r)
        return ed_t, ed_l, ed_b, ed_r
        #
        # renderer = self.app_ref.cropobject_list_renderer
        # # Top, left, height, width
        # m_coords = m_t, m_l, m_b - m_t, m_r - m_l
        # ed_b, ed_l, ed_height, ed_width = \
        #     renderer.model_coords_to_editor_coords(*m_coords)
        # ed_t = ed_b + ed_height
        # ed_r = ed_l + ed_width
        # return ed_t, ed_l, ed_b, ed_r


###############################################################################

class TrimmedLassoBoundingBoxSelectTool(LassoBoundingBoxSelectTool):
    current_cropobject_selection = ObjectProperty(None)
    current_cropobject_mask = ObjectProperty(None)

    def model_bbox_from_points(self, pos):
        """The trimming differs from the TrimTool because only points
        inside the convex hull of the lasso count towards trimming.

        ..warning:

            [Should be deprecated by now.)
            Assumes the lasso region is convex.
        """
        # Algorithm:
        #  - get bounding box of lasso in model coordinates
        #  - get model coordinates of points
        #  - get convex hull mask of these coordinates
        #  - apply mask of convex hull to the bounding box
        #    of the lasso selection
        #  - trim the masked image to get final model-space bounding box
        #  - recompute to editor-space
        #  - set finished box

        # Debug/profiling
        _start_time = time.clock()

        #  - get bounding box of lasso in model coordinates
        #    (we could just get uncut mask, but for trimming, we need
        #    m_points etc. anyway)
        point_set_as_tuples = [p for i, p in enumerate(zip(pos[:-1], pos[1:]))
                               if i % 2 == 0]

        m_points = [self.app_ref.image_scaler.point_widget2model(wX, wY)
                    for wX, wY in point_set_as_tuples]

        m_points = [(int(x), int(y)) for x, y in m_points]
        image = self.app_ref.annot_model.image
        mask = numpy.zeros((self.app_ref.image_scaler.model_height,
                            self.app_ref.image_scaler.model_width),
                           dtype=image.dtype)
        m_points_x, m_points_y = list(zip(*m_points))

        # Let's deal with points on the boundary or outside
        m_points_x = [max(0, min(x, self.app_ref.image_scaler.model_height - 1))
                      for x in m_points_x]
        m_points_y = [max(0, min(y, self.app_ref.image_scaler.model_width - 1))
                      for y in m_points_y]

        chi = polygon(m_points_x, m_points_y)
        mask[chi] = 1.0

        m_lasso_bbox = (min(m_points_x), min(m_points_y),
                        max(m_points_x), max(m_points_y))
        m_lasso_int_bbox = bbox_to_integer_bounds(*m_lasso_bbox)

        mask *= image
        mask = mask.astype(image.dtype)
        logging.info('T-Lasso: mask: {0} pxs'.format(old_div(mask.sum(), 255)))

        # - trim the masked image
        out_t, out_b, out_l, out_r = 1000000, 0, 1000000, 0
        img_t, img_l, img_b, img_r = m_lasso_int_bbox
        logging.info('T-Lasso: trimming with bbox={0}'.format(m_lasso_int_bbox))
        _trim_start_time = time.clock()
        # Find topmost and bottom-most nonzero row.
        for i in range(img_t, img_b):
            if mask[i, img_l:img_r].sum() > 0:
                out_t = i
                break
        for j in range(img_b, img_t, -1):
            if mask[j - 1, img_l:img_r].sum() > 0:
                out_b = j
                break
        # Find leftmost and rightmost nonzero column.
        for k in range(img_l, img_r):
            if mask[img_t:img_b, k].sum() > 0:
                out_l = k
                break
        for l in range(img_r, img_l, -1):
            if mask[img_t:img_b, l - 1].sum() > 0:
                out_r = l
                break
        _trim_end_time = time.clock()
        logging.info('T-Lasso: Trimming took {0:.4f} s'.format(_trim_end_time - _trim_start_time))

        logging.info('T-Lasso: Output={0}'.format((out_t, out_l, out_b, out_r)))

        # Rounding errors when converting m --> w --> m integers!
        #  - Output
        if (out_b > out_t) and (out_r > out_l):
            return out_t, out_l, out_b, out_r

    def model_selection_from_points(self, points):
        # This should go away anyway.
        model_bbox = self.model_bbox_from_points(points)
        if model_bbox is not None:
            t, l, b, r = model_bbox
            return {'top': t, 'left': l, 'bottom': b, 'right': r}
        else:
            return None

    def selection_from_points(self, points):
        model_bbox = self.model_bbox_from_points(points)
        if model_bbox is None:
            return None
        ed_t, ed_l, ed_b, ed_r = self.model_to_editor_bbox(*model_bbox)

        logging.info('T-Lasso: editor-coord output bbox {0}'
                     ''.format((ed_t, ed_l, ed_b, ed_r)))
        output = {'top': ed_t,
                  'bottom': ed_b,
                  'left': ed_l,
                  'right': ed_r}
        return output


###############################################################################


class MaskEraserTool(LassoBoundingBoxSelectTool):
    """Removes the given area from all selected symbols' masks."""

    def __init__(self, do_split, **kwargs):
        super(MaskEraserTool, self).__init__(**kwargs)
        self.do_split = do_split

    def on_current_cropobject_model_selection(self, instance, pos):
        """Here, instead of adding a new MungNode as the other lasso
        tools do, modify selected cropobjects' masks."""
        t, l, b, r = pos['top'], pos['left'], pos['bottom'], pos['right']
        bbox = bbox_to_integer_bounds(t, l, b, r)

        logging.info('MaskEraser: got bounding box: {0}'.format(bbox))

        for cropobject_view in self.app_ref.cropobject_list_renderer.view.selected_views:
            c = copy.deepcopy(cropobject_view._model_counterpart)
            # Guards:
            if c.mask is None:
                logging.info('MaskErarser: cropobject {0} has no mask.'
                             ''.format(c.objid))
                continue
            if not c.overlaps(bbox):
                logging.info('MaskErarser: cropobject {0} (bbox {1})'
                             'does not overlap.'
                             ''.format(c.objid, c.bounding_box))
                continue

            logging.info('MaskErarser: processing cropobject {0}.'
                         ''.format(c.objid))

            i_t, i_l, i_b, i_r = bbox_intersection(c.bounding_box, bbox)
            m_t, m_l, m_b, m_r = bbox_intersection(bbox, c.bounding_box)
            logging.info('MaskEraser: got cropobject intersection {0}'
                         ''.format((i_t, i_l, i_b, i_r)))
            logging.info('MaskEraser: got mask intersection {0}'
                         ''.format((m_t, m_l, m_b, m_r)))

            logging.info('MaskEraser: cropobject nnz previous = {0}'
                         ''.format(c.mask.sum()))

            # We need to invert the current mask, as we want to mask *out*
            # whatever is *in* the mask now.
            inverse_mask = c.mask.max() - self.current_cropobject_mask[m_t:m_b, m_l:m_r]
            c.mask[i_t:i_b, i_l:i_r] *= inverse_mask
            logging.info('MaskEraser: cropobject nnz after = {0}'
                         ''.format(c.mask.sum()))
            c.crop_to_mask()

            # We do the removal through the view, so that deselection
            # and other stuff is handled.
            cropobject_view.remove_from_model()

            if self.do_split:
                _next_objid = self._model.get_next_cropobject_id()
                output_cropobjects = split_cropobject_on_connected_components(c, _next_objid)
            else:
                output_cropobjects = [c]

            for c in output_cropobjects:
                # Now add the MungNode back to redraw. Note that this way,
                # the object's objid stays the same, which is essential for
                # maintaining intact inlinks and outlinks!
                logging.info('MaskEraser: New object data dict: {0}'
                             ''.format(c.data))
                self._model.add_cropobject(c)

                try:
                    new_view = self.app_ref.cropobject_list_renderer.view.get_cropobject_view(c.objid)
                    new_view.ensure_selected()
                except KeyError:
                    logging.info('MaskEraser: View for modified MungNode {0} has'
                                 ' not been rendered yet, cannot select it.'
                                 ''.format(c.objid))

        logging.info('MaskEraser: Forcing redraw.')
        self.app_ref.cropobject_list_renderer.redraw += 1
        self.app_ref.graph_renderer.redraw += 1

        self.editor_widgets['line_tracer'].clear()


class MaskAdditionTool(LassoBoundingBoxSelectTool):

    def on_current_cropobject_model_selection(self, instance, pos):
        """Here, instead of adding a new MungNode like the other
        Lasso tools, we instead modify the mask of selected MungNodes
        by adding the lasso-ed area."""
        c_lasso = self.app_ref.generate_cropobject_from_model_selection(
            selection=pos,
            mask=self.current_cropobject_mask)
        c_lasso.crop_to_mask()

        for cropobject_view in self.app_ref.cropobject_list_renderer.view.selected_views:
            c = copy.deepcopy(cropobject_view._model_counterpart)
            c.join(c_lasso)

            # Redraw:
            cropobject_view.remove_from_model()

            logging.info('MaskEraser: New object data dict: {0}'
                         ''.format(c.data))
            self._model.add_cropobject(c)

            # Try reselecting the selected objects:
            try:
                new_view = self.app_ref.cropobject_list_renderer.view.get_cropobject_view(c.objid)
                new_view.ensure_selected()
            except KeyError:
                logging.info('MaskEraser: View for modified MungNode {0} has'
                             ' not been rendered yet, cannot select it.'
                             ''.format(c.objid))

        logging.info('MaskAddition: Forcing redraw.')
        self.app_ref.cropobject_list_renderer.redraw += 1
        self.app_ref.graph_renderer.redraw += 1

        self.editor_widgets['line_tracer'].clear()


###############################################################################


class GestureSelectTool(LassoBoundingBoxSelectTool):
    """The GestureSelectTool tries to find the best approximation
    to a user gesture, as though the user is writing the score
    instead of annotating it.

    Run bounds
    ----------

    * Top: topmost coordinate of all accepted runs.
    * Bottom: bottom-most coordinate of all accepted runs.
    * Left: leftmost coordinates of all runs over the lower limit.
    * Right: rightmost coordinate of all runs over the lower limit.

    NOTE: Currently only supports horizontal strokes

    NOTE: Not resistant to the gesture leaving and re-entering
        a stroke region.
    """
    current_cropobject_selection = ObjectProperty(None)
    current_cropobject_mask = ObjectProperty(None)

    def create_editor_widgets(self):
        editor_widgets = collections.OrderedDict()
        editor_widgets['line_tracer'] = LineTracer()
        editor_widgets['line_tracer'].bind(points=self.current_selection_from_points)
        return editor_widgets

    def current_selection_from_points(self, instance, pos):

        # Map points to model
        #  - get model coordinates of points
        e_points = numpy.array([list(p) for i, p in enumerate(zip(pos[:-1], pos[1:]))
                                if i % 2 == 0])
        # We don't just need the points, we need their order as well...
        m_points = numpy.array([self.app_ref.map_point_from_editor_to_model(*p)
                                for p in e_points]).astype('uint16')
        # Make them unique
        m_points_uniq = numpy.array([m_points[0]] +
                                    [m_points[i] for i in range(1, len(m_points))
                                     if (m_points[i] - m_points[i - 1]).sum() == 0.0])

        logging.info('Gesture: total M-Points: {0}, unique: {1}'
                     ''.format(len(m_points), len(m_points_uniq)))

        # Get image
        image = self.app_ref.annot_model.image

        # Now the intelligent part starts.
        #  - If more vertical than horizontal, record horizontal runs.
        e_sel = self.selection_from_points(pos)
        m_bbox = self.app_ref.generate_model_bbox_from_selection(e_sel)
        m_int_bbox = bbox_to_integer_bounds(*m_bbox)

        height = m_int_bbox[2] - m_int_bbox[0]
        width = m_int_bbox[3] - m_int_bbox[1]

        is_vertical = False
        if height >= 2 * width:
            is_vertical = True

        if is_vertical:
            raise NotImplementedError('Sorry, currently only supporting horizontal'
                                      ' strokes.')

        # TODO: make points also unique column-wise

        #  - Get all vertical runs the stroke goes through
        #      - Find stroke mask (approximate with straight lines) and
        #        collect all stroke points
        #      - For each point:
        stroke_mask = numpy.zeros(image.shape, dtype=image.dtype)
        all_points = [[], []]
        for i, (a, b) in enumerate(zip(m_points_uniq[:-1], m_points_uniq[1:])):
            l = line(a[0], a[1], b[0], b[1])
            all_points[0].extend(list(l[0]))
            all_points[1].extend(list(l[1]))
            stroke_mask[l] = 1

        runs = []
        # Each point's run is represented as a [top, bottom] pair,
        # empty runs are represented as (x, x).
        for x, y in zip(*all_points):
            t = x
            while (image[t, y] != 0) and (t >= 0):
                t -= 1
            b = x
            while (image[b, y] != 0) and (b >= 0):
                b += 1
            runs.append([t, b])

        #  - Compute stroke width histograms from connected components.
        run_widths = numpy.array([b - t for t, b in runs])
        nnz_run_widths = numpy.array([w for w in run_widths if w > 0])
        # Average is too high because of crossing strokes, we should use median.
        rw_med = numpy.median(nnz_run_widths)
        logging.info('Gesture: Collected stroke vertical runs, {0} in total,'
                     ' avg. width {1:.2f}'.format(len(runs),
                                                  rw_med))

        #  - Compute run width bounds
        rw_lower = 2
        rw_upper = int(rw_med * 1.1 + 1)

        #  - Sort out which runs are within, under, and over the width range
        runs_mask = [rw_lower <= (b - t) <= rw_upper for t, b in runs]
        runs_under = [(b - t) < rw_lower for t, b in runs]
        runs_over = [(b - t) > rw_upper for t, b in runs]

        runs_accepted = [r for i, r in enumerate(runs) if runs_mask[i]]
        ra_npy = numpy.array(runs_accepted)

        logging.info('Gesture: run bounds [{0}, {1}]'.format(rw_lower, rw_upper))
        logging.info('Gesture: Accepted: {0}, under: {1}, over: {2}'
                     ''.format(len(runs_accepted), sum(runs_under), sum(runs_over)))

        #  - Get run bounds
        out_t = ra_npy[:, 0].min()
        out_b = ra_npy[:, 1].max()
        out_l = min([all_points[1][i] for i, r in enumerate(runs_under) if not r])
        out_r = max([all_points[1][i] for i, r in enumerate(runs_under) if not r])

        logging.info('Gesture: model bounds = {0}'.format((out_t, out_l, out_b, out_r)))

        if (out_b > out_t) and (out_r > out_l):
            ed_t, ed_l, ed_b, ed_r = self.model_to_editor_bbox(out_t,
                                                               out_l,
                                                               out_b,
                                                               out_r)

            logging.info('Gesture: editor-coord output bbox {0}'
                         ''.format((ed_t, ed_l, ed_b, ed_r)))
            self.current_cropobject_selection = {'top': ed_t,
                                                 'bottom': ed_b,
                                                 'left': ed_l,
                                                 'right': ed_r}


###############################################################################


class BaseListItemViewsOperationTool(MUSCIMarkerTool):
    """This is a base class for tools manipulating ListItemViews.

    Override select_applicable_objects to define how the ListItemViews
    should be selected.

    Override ``@property list_view`` to point to the desired ListView.

    Override ``@property available_views`` if the default
    ``self.list_view.container.children[:]`` is not correct.

    Override the ``apply_operation`` method to get tools that actually do
    something to the MungNodeViews that correspond to MungNodes
    overlapping the lasso-ed area."""
    use_mask_to_determine_selection = BooleanProperty(False)

    line_color = ListProperty([0.6, 0.6, 0.6])

    forgetful = BooleanProperty(True)
    '''If True, will always forget prior selection. If False, will
    be "additive".'''

    active_selection = BooleanProperty(True)
    '''If True, will show the current state of the selection.'''

    def __init__(self, app, editor_widget, command_widget, active_selection=True,
                 **kwargs):

        # Settings like this have to be provided *before* create_editor_widgets
        # is called by super.__init__
        self.active_selection = active_selection
        logging.info('Toolkit: __init__ got active selection: {0}'
                     ''.format(self.active_selection))

        super(BaseListItemViewsOperationTool, self).__init__(app=app,
                                                             editor_widget=editor_widget,
                                                             command_widget=command_widget,
                                                             **kwargs)

    def create_editor_widgets(self):
        editor_widgets = collections.OrderedDict()
        editor_widgets['line_tracer'] = LineTracer()
        editor_widgets['line_tracer'].line_color = self.line_color
        editor_widgets['line_tracer'].bind(points=self.final_select_applicable_objects)

        if self.active_selection:
            editor_widgets['line_tracer'].bind(on_touch_down=self.process_active_selection_start)
            editor_widgets['line_tracer'].bind(on_touch_move=self.process_active_selection_move)
            editor_widgets['line_tracer'].bind(on_touch_up=self.process_active_selection_end)
        else:
            logging.info('Toolkit: active selection not requested')

        return editor_widgets

    ##########################################################################
    # Active selection behavior

    # _active_selection_object_touched = DictProperty(None, allownone=True)
    # '''Maintains the list of objects that have been passed through and selected
    # by the traced line itself. For these, we are sure they will get selected.'''
    #
    # _active_selection_object_in = DictProperty(None, allownone=True)
    # '''Maintains the list of objects that are currently affected
    # by the complement of the selection line (straigt line from start
    # to end of current line), but have not been directly touched.'''
    #
    # _active_selection_object_passed = DictProperty(None, allownone=True)
    # '''Maintains the list of objects that would currently get selected, if
    # the on_touch_up() signal came, although they have not been directly
    # touched and the complement line is not currently touching them.'''

    _active_selection_slow_mode = BooleanProperty(False)
    '''Slow mode: only check for active selection once every 10 touch_move
    events.'''

    _active_selection_slow_mode_threshold = NumericProperty(30000)
    '''Empirically measured slow mode threshold.'''

    _active_selection_slow_mode_counter = NumericProperty(1)
    _active_selection_slow_mode_modulo = NumericProperty(10)
    '''Active selection in slow mode should not take more than 0.001
    seconds per move event. E.g., if one selection is taking 0.01 s,
    then it has to be spread over 10 events. If it takes 0.5 s, it has
    to be spread over 50 events.

    The time is measured every time active selection is run in slow mode.
    The slow_mode_modulo is adjusted accordingly and the counter is reset.
    '''

    _active_selection_target_time_per_event = NumericProperty(0.01)
    '''The desired amortized time taken by the active selection
    computation per on_touch_move event.'''

    def process_active_selection_start(self, tracer, touch):
        # Unselect all
        if self.forgetful:
            for v in self.available_views:
                if v.is_selected:
                    v.dispatch('on_release')

    def process_active_selection_move(self, tracer, touch):
        # This has the problem that it only includes the collided
        # objects, not those "inside"
        # for v in self.available_views:
        #     if v.collide_point(touch.x, touch.y):
        #         if not v.is_selected:
        #             v.dispatch('on_release')

        points = touch.ud['line'].points
        m_points = self.editor_to_model_points(points)
        # logging.debug('Active selection: {0} points in line'.format(len(m_points)))
        self._process_active_selection_slow_mode(m_points)

        if self._active_selection_slow_mode:
            if self._active_selection_slow_mode_counter % self._active_selection_slow_mode_modulo == 0:
                # Let's try running "experimental selection"
                # logging.info('Active selection: checking in slow mode')
                _t_start = time.clock()
                self.provisional_select_applicable_objects(instance=None,
                                                           points=touch.ud['line'].points)
                _t_end = time.clock()
                time_taken = (_t_end - _t_start)
                # Set new modulo so that the expected time per event is 0.001.
                # Later on, this may cause noticeable lag in the selection, but
                # hopefully not so much in the lasso.
                self._active_selection_slow_mode_modulo = max(1, min(
                    int(old_div(time_taken, self._active_selection_target_time_per_event)), 30))
                logging.debug('Active selection: time take: {0}, setting modulo to {1}'
                              ''.format(time_taken, self._active_selection_slow_mode_modulo))
                self._active_selection_slow_mode_counter = 1
            else:
                self._active_selection_slow_mode_counter += 1
        else:
            logging.debug('Active selection: checking in normal mode')
            self.provisional_select_applicable_objects(instance=None,
                                                       points=touch.ud['line'].points)

    def process_active_selection_end(self, tracer, touch):
        pass

    def _process_active_selection_slow_mode(self, points):
        m_points_x, m_points_y = list(zip(*points))
        xmin, xmax = min(m_points_x), max(m_points_x)
        ymin, ymax = min(m_points_y), max(m_points_y)

        # logging.debug('Active selection: checking slow mode with range'
        #               ' ({0}, {1}), ({2}, {3})'
        #               ''.format(xmin, xmax, ymin, ymax))
        is_slow = True
        # if (xmax - xmin) * (ymax - ymin) < self._active_selection_slow_mode_threshold:
        #    is_slow = False

        if self._active_selection_slow_mode != is_slow:
            logging.debug('Active selection: slow mode: changing to {0}'.format(is_slow))
            self._active_selection_slow_mode_counter = 1

        self._active_selection_slow_mode = is_slow

    ##########################################################################
    # Computing the selection from a set of points

    def provisional_select_applicable_objects(self, instance, points):
        self.select_applicable_objects(instance, points, do_clear_tracer=False)

    def final_select_applicable_objects(self, instance, points):
        self.select_applicable_objects(instance, points, do_clear_tracer=True)

    def select_applicable_objects(self, instance, points, do_clear_tracer=True):
        raise NotImplementedError()

    @property
    def list_view(self):
        raise NotImplementedError()

    @property
    def available_views(self):
        return [c for c in self.list_view.container.children[:]]

    def apply_operation(self, item_view):
        """Override this method in child Tools to make this actually
        do something to the overlapping MungNodeViews."""
        pass


class CropObjectViewsSelectTool(BaseListItemViewsOperationTool):
    """Select the activated MungNodeViews."""

    def __init__(self, ignore_staff=False, **kwargs):
        super(CropObjectViewsSelectTool, self).__init__(**kwargs)
        self.ignore_staff = ignore_staff

    forgetful = BooleanProperty(True)
    '''If True, will always forget prior selection. If False, will
    be "additive".'''

    line_color = ListProperty([1.0, 0.5, 1.0])

    def select_applicable_objects(self, instance, points, do_clear_tracer=True):
        # Get the model mask
        _t_start = time.clock()

        m_points = self.editor_to_model_points(points)

        _t_points = time.clock()

        # filtered_m_points = self._filter_polygon_points_to_relevant_for_selection(m_points)
        # Possible speedup: discard points that cannot have any further
        # effect on object selection/deselection.
        # The polygon() implementation is already algorithmically
        # efficient.

        model_mask = self.model_mask_from_points(m_points)

        _t_middle = time.clock()

        # Find all MungNodes that overlap
        objids = [objid for objid, c in self._model.cropobjects.items()
                  if image_mask_overlaps_cropobject(model_mask, c,
                                                    use_cropobject_mask=self.use_mask_to_determine_selection)]

        if self.ignore_staff:
            objids = [objid for objid in objids
                      if self._model.cropobjects[objid].clsname not in _CONST.STAFF_CROPOBJECT_CLSNAMES]

        _t_end = time.clock()
        # logging.info('select_applicable_objects: points and mask took'
        #              ' {0:.5f} ({1:.5f}/{2:.5f}, collision checks took {3:.5f}'
        #              ''.format(_t_middle - _t_start,
        #                        _t_points - _t_start, _t_middle  - _t_points,
        #                        _t_end - _t_middle))

        if do_clear_tracer:
            logging.info('select_applicable_objects: clearing tracer')
            self.editor_widgets['line_tracer'].clear()

        # Unselect
        if self.forgetful:
            for v in self.available_views:
                if v.is_selected:
                    v.dispatch('on_release')

        # Mark their views as selected
        applicable_views = [v for v in self.available_views
                            if v.objid in objids]
        logging.info('select_applicable_objects: found {0} objects'
                     ''.format(len(applicable_views)))
        for c in applicable_views:
            self.apply_operation(c)

    def apply_operation(self, item_view):
        if not item_view.is_selected:
            # item_view.select()
            item_view.dispatch('on_release')

    @property
    def list_view(self):
        return self.app_ref.cropobject_list_renderer.view

    # @property
    # def available_views(self):
    #    return self.list_view.rendered_views

    def _filter_polygon_points_to_relevant_for_selection(self, m_points):
        """We can filter out some points in the polygon if we can be
        sure that if we leave them out, the final selection will be
        the same as if we left them in."""
        return m_points


class EdgeViewsSelectTool(BaseListItemViewsOperationTool):
    """Selects all edges that lead to/from MungNodes overlapped
    by the selection."""
    line_color = ListProperty([1.0, 0.0, 0.0])

    def select_applicable_objects(self, instance, points, do_clear_tracer=True):
        # Get the model mask
        m_points = self.editor_to_model_points(points)
        model_mask = self.model_mask_from_points(m_points)

        # Find all Edges that overlap
        objid_pairs = []
        for e in self.available_views:
            # logging.info('Edge {0} --> {1}'.format(e.edge[0], e.edge[1]))
            c_start = self._model.cropobjects[e.start_objid]
            c_end = self._model.cropobjects[e.end_objid]
            if c_start.objid == 224 and c_end.objid == 225:
                sx, sy = c_start.middle
                ex, ey = c_end.middle
                mx, my = old_div((sx + ex), 2), old_div((sy + ey), 2)
                logging.warn('Edge 224 --> 225: middle points '
                             '{0}, {1} -- mask: {2}'
                             ''.format(c_start.middle, c_end.middle,
                                       model_mask[mx, my]))
            # This is a little hack-ish, because the assumptions about
            # what is up and what is left are wrong...?
            if image_mask_overlaps_model_edge(model_mask,
                                              c_start.middle,
                                              c_end.middle):
                objid_pairs.append((e.start_objid, e.end_objid))

        # Find all MungNodes that overlap
        # objids = [objid for objid, c in self._model.cropobjects.iteritems()
        #           if image_mask_overlaps_cropobject(model_mask, c,
        #             use_cropobject_mask=self.use_mask_to_determine_selection)]

        if do_clear_tracer:
            self.editor_widgets['line_tracer'].clear()

        # Mark their views as selected
        applicable_views = [v for v in self.available_views
                            if v.edge in objid_pairs]
        for c in applicable_views:
            self.apply_operation(c)

    def apply_operation(self, item_view):
        if not item_view.is_selected:
            item_view.dispatch('on_release')

    @property
    def list_view(self):
        return self.app_ref.graph_renderer.view

    # @property
    # def available_views(self):
    #    return self.list_view.rendered_views


class CropObjectViewsParseTool(CropObjectViewsSelectTool):

    def select_applicable_objects(self, instance, points, do_clear_tracer=True):
        super(CropObjectViewsParseTool, self).select_applicable_objects(instance, points,
                                                                        do_clear_tracer=do_clear_tracer)
        self.list_view.parse_current_selection()


###############################################################################


# NOT IMPLEMENTED
class NoteSelectTool(AddSymbolTool):
    """Given a bounding box, splits it into a stem and notehead bounding box.

    [NOT IMPLEMENTED]"""
    current_cropobject_selection = ObjectProperty(None)

    def create_editor_widgets(self):
        editor_widgets = collections.OrderedDict()
        editor_widgets['bbox_tracer'] = ConnectedComponentBoundingBoxTracer()
        editor_widgets['bbox_tracer'].bind(current_finished_bbox=self.process_note)

    def process_note(self):
        raise NotImplementedError()

        current_postprocessed_bbox = self.editor_widgets['bbox_tracer'].current_postprocessed_bbox
        self.current_cropobject_selection = current_postprocessed_bbox


###############################################################################

# Image processing tools

class RegionBinarizeTool(MUSCIMarkerTool):
    """Binarize the region in the bounding box using Otsu binarization."""

    def __init__(self, retain_foreground, **kwargs):
        super(RegionBinarizeTool, self).__init__(**kwargs)
        self.retain_foreground = retain_foreground

    def create_editor_widgets(self):
        editor_widgets = collections.OrderedDict()
        editor_widgets['bbox_tracer'] = BoundingBoxTracer()
        editor_widgets['bbox_tracer'].bind(
            current_finished_bbox=self.binarize)
        return editor_widgets

    def binarize(self, instance, pos):
        """Binarize the selected region and update the annotated image."""

        # Get model bbox
        ed_t, ed_l, ed_b, ed_r = pos['top'], pos['left'], \
                                 pos['bottom'], pos['right']
        m_t, m_l, m_b, m_r = self.editor_to_model_bbox(ed_t, ed_l, ed_b, ed_r)
        m_t, m_l, m_b, m_r = bbox_to_integer_bounds(m_t, m_l, m_b, m_r)

        _binarization_start = time.clock()

        # Crop and binarize
        image = self.app_ref.annot_model.image * 1
        crop = image[m_t:m_b, m_l:m_r] * 1

        if crop.sum() == 0:
            logging.info('RegionBinarizeTool: selected single-color region,'
                         ' cannot binarize anything.')
            self.editor_widgets['bbox_tracer'].clear()
            return

        nnz_crop = crop.ravel()[numpy.flatnonzero(crop)]
        nnz_crop_threshold = threshold_otsu(nnz_crop)

        # binarized_crop_threshold = threshold_otsu(crop)
        crop[crop < nnz_crop_threshold] = 0
        if not self.retain_foreground:
            crop[crop >= nnz_crop_threshold] = 255
        output_crop = crop

        # sauvola_thresholds = threshold_sauvola(crop)
        # sauvola_mask = crop > sauvola_thresholds
        # output_crop = sauvola_mask * crop

        image[m_t:m_b, m_l:m_r] = output_crop

        _update_start = time.clock()

        # Update image
        self.app_ref.update_image(image)

        _binarization_end = time.clock()
        logging.info('RegionBinarizeTool: binarization took {0:.3f} s,'
                     ' image update took {1:.3f} s'
                     ''.format(_update_start - _binarization_start,
                               _binarization_end - _update_start))

        # Clean up
        self.editor_widgets['bbox_tracer'].clear()


class BackgroundLassoTool(LassoBoundingBoxSelectTool):
    """Set the selected area as image background."""

    def on_current_cropobject_model_selection(self, instance, pos):
        # Ask the app to build MungNode from the bbox.
        logging.info('BackgroundLassoTool: fired on_current_cropobject_model_selection with pos={0}'
                     ''.format(pos))

        pos = self.current_cropobject_model_selection
        m_t, m_l, m_b, m_r = pos['top'], pos['left'], \
                             pos['bottom'], pos['right']
        m_t, m_l, m_b, m_r = bbox_to_integer_bounds(m_t, m_l, m_b, m_r)

        image = self.app_ref.annot_model.image * 1
        crop = image[m_t:m_b, m_l:m_r] * 1

        if crop.shape != (m_b - m_t, m_r - m_l):
            raise ValueError('BackgroundLassoTool: crop bbox {0} does not correspond'
                             ' to mask shape {1}!'.format(
                (m_t, m_l, m_b, m_r), crop.shape
            ))

        crop[self.current_cropobject_mask == 1] = 0
        output_crop = crop

        image[m_t:m_b, m_l:m_r] = output_crop

        self.app_ref.update_image(image)

        # Automatically clears the bounding box (it gets rendered as the new symbol
        # gets recorded).
        self.editor_widgets['line_tracer'].clear()


class BackgroundFillTool(LassoBoundingBoxSelectTool):
    """This is used for getting rid of background that did not go away
    in binarization more smartly than the plain backgrounding lasso.
    It takes the lightest shade in the given area, and within a 200-px
    bounding box (+100/-100), removes everything that is darker than
    the given pixel by at least 8 intensity points. [NOT IMPLEMENTED]"""

    def on_current_cropobject_model_selection(self, instance, pos):
        # Ask the app to build MungNode from the bbox.
        logging.info('BackgroundFillTool: fired on_current_cropobject_model_selection with pos={0}'
                     ''.format(pos))

        raise NotImplementedError()

        pos = self.current_cropobject_model_selection
        m_t, m_l, m_b, m_r = pos['top'], pos['left'], \
                             pos['bottom'], pos['right']
        m_t, m_l, m_b, m_r = bbox_to_integer_bounds(m_t, m_l, m_b, m_r)

        image = self.app_ref.annot_model.image * 1
        crop = image[m_t:m_b, m_l:m_r] * 1

        if crop.shape != (m_b - m_t, m_r - m_l):
            raise ValueError('BackgroundFillTool: crop bbox {0} does not correspond'
                             ' to mask shape {1}!'.format(
                (m_t, m_l, m_b, m_r), crop.shape
            ))

        crop[self.current_cropobject_mask == 1] = 0
        output_crop = crop

        image[m_t:m_b, m_l:m_r] = output_crop

        self.app_ref.update_image(image)

        # Automatically clears the bounding box (it gets rendered as the new symbol
        # gets recorded).
        self.editor_widgets['line_tracer'].clear()


##############################################################################
# Interface for detection! Highly experimental.

class SymbolDetectionTool(MUSCIMarkerTool):
    """Runs the detector for the currently selected MungNode class
    on a selected region.

    Requires having a detection server running on a configured host/port.
    The detection server is currently not open-source.
    """

    def __init__(self, use_current_class, clsnames, **kwargs):
        super(SymbolDetectionTool, self).__init__(**kwargs)
        self.use_current_class = use_current_class
        self.clsnames = clsnames

    def create_editor_widgets(self):
        editor_widgets = collections.OrderedDict()
        editor_widgets['bbox_tracer'] = BoundingBoxTracer()
        editor_widgets['bbox_tracer'].bind(
            current_finished_bbox=self.run_detection)
        return editor_widgets

    def run_detection(self, instance, pos):
        # Get model bbox
        ed_t, ed_l, ed_b, ed_r = pos['top'], pos['left'], \
                                 pos['bottom'], pos['right']
        m_t, m_l, m_b, m_r = self.editor_to_model_bbox(ed_t, ed_l, ed_b, ed_r)
        m_t, m_l, m_b, m_r = bbox_to_integer_bounds(m_t, m_l, m_b, m_r)

        if self.use_current_class:
            clsnames = None
        else:
            clsnames = self.clsnames

        self.app_ref.annot_model.call_object_detection(bounding_box=(m_t, m_l, m_b, m_r),
                                                       clsnames=clsnames)

        self.editor_widgets['bbox_tracer'].clear()


##############################################################################
# This is the toolkit's interface to the UI elements.

tool_dispatch = {
    'viewing_tool': ViewingTool,
    'add_symbol_tool': AddSymbolTool,
    'trimmed_select_tool': TrimmedSelectTool,
    'connected_select_tool': ConnectedSelectTool,
    'lasso_select_tool': LassoBoundingBoxSelectTool,
    'trimmed_lasso_select_tool': TrimmedLassoBoundingBoxSelectTool,
    'gesture_select_tool': GestureSelectTool,
    'cropobject_views_select_tool': CropObjectViewsSelectTool,
    'edge_views_select_tool': EdgeViewsSelectTool,
    'cropobject_views_parse_tool': CropObjectViewsParseTool,
    'mask_eraser_tool': MaskEraserTool,
    'mask_addition_tool': MaskAdditionTool,
    'region_binarize_tool': RegionBinarizeTool,
    'background_lasso_tool': BackgroundLassoTool,
    'symbol_detection_tool': SymbolDetectionTool,
    'average_symbol_tool': AverageSymbolTool,
}


def get_tool_kwargs_dispatch(name):
    no_kwarg_tools = {
        'viewing_tool': dict(),
        'add_symbol_tool': dict(),
        'trimmed_select_tool': dict(),
        'connected_select_tool': dict(),
        'lasso_select_tool': dict(),
        'gesture_select_tool': dict(),
        # 'region_binarize_tool': dict(),
        'background_lasso_tool': dict(),
        'average_symbol_tool': dict(),
    }

    if name in no_kwarg_tools:
        return no_kwarg_tools[name]

    app = App.get_running_app()
    conf = app.config

    if name == 'symbol_detection_tool':
        _use_ccls = conf.get('toolkit', 'detection_use_current_class')
        use_ccls = _safe_parse_bool_from_conf(_use_ccls)
        clsnames = conf.get('toolkit', 'detection_classes').split(',')
        return {'use_current_class': use_ccls,
                'clsnames': clsnames}

    if name == 'region_binarize_tool':
        _retain_fg = conf.get('toolkit', 'binarization_retain_foreground')
        retain_fg = _safe_parse_bool_from_conf(_retain_fg)
        return {'retain_foreground': retain_fg}

    if name == 'trimmed_lasso_select_tool':
        _dhl_str = conf.get('toolkit', 'trimmed_lasso_helper_line')
        do_helper_line = _safe_parse_bool_from_conf(_dhl_str)
        helper_line_min_length = int(conf.get('toolkit', 'trimmed_lasso_helper_line_length'))
        return {'do_helper_line': do_helper_line,
                'helper_line_min_length': helper_line_min_length}

    if name == 'mask_eraser_tool':
        _dhl_str = conf.get('toolkit', 'trimmed_lasso_helper_line')
        do_helper_line = _safe_parse_bool_from_conf(_dhl_str)
        _splitter_str = conf.get('toolkit', 'split_on_eraser')
        do_split = _safe_parse_bool_from_conf(_splitter_str)
        return {'do_helper_line': do_helper_line,
                'do_split': do_split}

    if name == 'mask_addition_tool':
        _dhl_str = conf.get('toolkit', 'trimmed_lasso_helper_line')
        do_helper_line = _safe_parse_bool_from_conf(_dhl_str)
        return {'do_helper_line': do_helper_line}

    if name == 'cropobject_views_select_tool':
        _as_str = conf.get('toolkit', 'active_selection')
        active_selection = _safe_parse_bool_from_conf(_as_str)
        _ignore_staff_str = conf.get('toolkit', 'selection_ignore_staff')
        ignore_staff = _safe_parse_bool_from_conf(_ignore_staff_str)
        logging.info('Toolkit: got active_selection={0}, ignore_staff={1}'
                     ''.format(active_selection, ignore_staff))
        return {'active_selection': active_selection,
                'ignore_staff': ignore_staff}

    if name == 'edge_views_select_tool':
        _as_str = conf.get('toolkit', 'active_selection')
        active_selection = _safe_parse_bool_from_conf(_as_str)
        logging.info('Toolkit: got active_selection={0}'
                     ''.format(active_selection))
        return {'active_selection': active_selection}

    if name == 'cropobject_views_parse_tool':
        # Doesn't make sense here without a way to undo the line,
        # it would just be frustrating.
        active_selection = False
        logging.info('Toolkit: got active_selection={0}'
                     ''.format(active_selection))
        _ignore_staff_str = conf.get('toolkit', 'selection_ignore_staff')
        ignore_staff = _safe_parse_bool_from_conf(_ignore_staff_str)
        logging.info('Toolkit: got active_selection={0}, ignore_staff={1}'
                     ''.format(active_selection, ignore_staff))
        return {'active_selection': active_selection,
                'ignore_staff': ignore_staff}


def _safe_parse_bool_from_conf(conf_str):
    if conf_str == 'True':
        return True
    elif conf_str == 'False':
        return False
    else:
        return bool(int(conf_str))
