"""This module implements a class that..."""
from __future__ import print_function, unicode_literals
from __future__ import division

from past.utils import old_div
import copy
import logging
import pprint

import math

from mung.inference.constants import _CONST

from kivy.adapters.dictadapter import DictAdapter
from kivy.app import App
from kivy.clock import  Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, Rectangle
from kivy.properties import ObjectProperty, NumericProperty, BooleanProperty, ListProperty, DictProperty
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.listview import SelectableView, ListView, CompositeListItem
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

__version__ = "0.0.1"
__author__ = "Jan Hajic jr."


class EdgeView(SelectableView, ToggleButton):
    """The EdgeView class represents a CropObject attachment edge.

    Currently: only a very simple """
    selected_color = ListProperty([1., 0., 0., 0.5])
    deselected_color = ListProperty([1., 0., 0., 0.3])

    vert_start = NumericProperty()
    horz_start = NumericProperty()

    vert_end = NumericProperty()
    horz_end = NumericProperty()

    _collide_threshold = NumericProperty(20.0)
    '''Distance from the edge line at which to collide touch events
    with the EdgeView. Given in *screen* pixels, to behave consistently
    regardless of editor scale.'''

    _start_node_size = 2.0

    STAFF_CROPOBJECT_CLASSES = ['staff_line', 'staff_space', 'staff']

    def __init__(self,
                 cropobject_from, cropobject_to, edge_label=None,
                 rgb=(1, 0, 0), **kwargs):
        """Initialize EdgeView: draw a red line from the middle
        of ``obj_from`` to the middle of ``obj_to``.

        Currently does NOT do the conversion from model-world to editor-world.
        It expects the cropobj_from and cropobj_to to already be editor-world.
        """
        super(EdgeView, self).__init__(**kwargs)

        self.start_objid = cropobject_from.objid
        self.end_objid = cropobject_to.objid
        self.label = edge_label

        ##### Generating endpoint positions.

        self._generate_start_and_end_points(cropobject_from, cropobject_to)

        self._line_width = 1
        self._selected_line_width = 2

        ##### Handling the button stuff -- temporary...
        self.text = ''   # We don't want any text showing up

        ###### Generating the colors
        # This might be endpoint classes-specific, or more generally
        # edge class-specific. Right now we are just making it up
        # on the spot through generate_edge_view_color()
        rgb, alpha = self._generate_edge_view_color(cropobject_from,
                                                    cropobject_to,
                                                    edge_label)

        self.rgb = rgb

        r, g, b = rgb
        self.selected_color = r, g, b, min([1.0, alpha * 1.8])
        self.deselected_color = r, g, b, alpha
        self.alpha = alpha  # Recorded for future color changes on class change

        # Overriding the default button color and border behavior
        self.background_color = self.deselected_color
        self.background_normal = ''
        self.background_down = ''
        self.border = 0, 0, 0, 0

        #######

        # We have drawn the line to our own canvas, but where
        # is *this* widget? Where are this widget's canvas w.r.t.
        # the editor? We need to position ourselves!
        #  -- this is a bit tricky, though, because this widget is not
        #     a rectangle. It should not react to touches outside
        #     the diagonal. So, we should override collide_point().
        h = max(max(self.horz_start, self.horz_end) - min(self.horz_start, self.horz_end),
                self._line_width)
        w = max(max(self.vert_start, self.vert_end) - min(self.vert_start, self.vert_end),
                self._line_width)
        self.size = h, w
        self.size_hint = (None, None)
        self.pos = min(self.horz_start, self.horz_end), min(self.vert_start, self.vert_end)

        # Overriding default release
        self.always_release = False

        # logging.debug('EdgeView: Initialized for edge {0}'
        #               #', with pos={1}, size={2}'
        #               ''.format(self.edge, self.pos, self.size))
        self.do_render()

        self.register_event_type('on_key_captured')
        self.create_bindings()

    @property
    def edge(self):
        return self.start_objid, self.end_objid

    @property
    def graph(self):
        return App.get_running_app().annot_model.graph

    @property
    def model(self):
        return App.get_running_app().annot_model

    @property
    def edge_label(self):
        return self.graph.edges[self.edge]

    @property
    def bottom(self):
        return self.y

    @property
    def left(self):
        return self.x

    def _start_and_end_invisibly_close(self):
        delta_h = self.horz_end - self.horz_start
        delta_v = self.vert_end - self.vert_start
        return (delta_h ** 2 + delta_v ** 2) < (self._start_node_size * 1.615)

    def _adjust_for_invisible_end(self):
        self.horz_end += self._start_node_size * 1.1
        self.vert_end -= self._start_node_size * 0.45

    def _generate_start_and_end_points(self, cropobject_from, cropobject_to):
        # Another shitty, shitty x/y switch. Why can't people use
        # (top, left, bottom, right) names???
        self.vert_start = cropobject_from.x + (old_div(cropobject_from.height, 2))
        self.horz_start = cropobject_from.y + (old_div(cropobject_from.width, 2))

        self.vert_end = cropobject_to.x + (old_div(cropobject_to.height, 2))

        # Edges that lead from non-staff to staff objects
        # only point a bit to the right.
        if cropobject_to.clsname in _CONST.STAFF_CROPOBJECT_CLSNAMES:
            if cropobject_from.clsname in _CONST.STAFF_CROPOBJECT_CLSNAMES:
                self.horz_end = cropobject_to.y + (old_div(cropobject_to.width, 2))
            else:
                self.horz_end = cropobject_from.y + 20
        else:
            self.horz_end = cropobject_to.y + (old_div(cropobject_to.width, 2))

        if self._start_and_end_invisibly_close():
            self._adjust_for_invisible_end()

    def _generate_edge_view_color(self,
                                  cropobject_from, cropobject_to,
                                  edge_label=None):
        """Generates the edge view color based on the from/to CropObjects
        and the edge label.

        Designed as a temporary solution to differentiating staff-related
        edges.

        Current operations
        ------------------

        * Non-staff attachment edges are red
        * Staff attachment edges are dark purple
        """
        DEFAULT_RGB = (1, 0, 0)
        DEFAULT_ALPHA = 0.3

        rgb, alpha = DEFAULT_RGB, DEFAULT_ALPHA

        if (cropobject_from.clsname in self.STAFF_CROPOBJECT_CLASSES) \
            or (cropobject_to.clsname in self.STAFF_CROPOBJECT_CLASSES):
                rgb = (0.8, 0, 0.8)
                alpha = 0.3

        elif edge_label == 'Precedence':
            rgb = (0.4, 1.0, 0.0)
            alpha = 0.3

        elif edge_label == 'Simultaneity':
            rgb = (0.0, 1.0, 1.0)
            alpha = 0.3

        return rgb, alpha

    def create_bindings(self):
        # logging.debug('EdgeView\t{0}: Creating bindings'.format(self.edge))
        Window.bind(on_key_down=self.on_key_down)
        Window.bind(on_key_up=self.on_key_up)
        #logging.info('EdgeView\t{0}: Current on_key_down total observers: {1}, obs:\n{2}'
        #             ''.format(self.edge, len(Window.get_property_observers('on_key_down')),
        #                       pprint.pformat(Window.get_property_observers('on_key_down'))))

    def remove_bindings(self):
        # logging.debug('EdgeView\t{0}: Removing bindings'.format(self.edge))
        Window.unbind(on_key_down=self.on_key_down)
        Window.unbind(on_key_up=self.on_key_up)

    def on_key_down(self, window, key, scancode, codepoint, modifier):

        if not self.is_selected:
            return False

        dispatch_key = self.keypress_to_dispatch_key(key, scancode, codepoint, modifier)
        #logging.info('EdgeView\t{0}: Handling key {1}, self.is_selected={2}'
        #             ''.format(self.edge, dispatch_key, self.is_selected))
        is_handled = self.handle_dispatch_key(dispatch_key)
        if is_handled:
            self.dispatch('on_key_captured')

        return False

    def handle_dispatch_key(self, dispatch_key):
        """Does the "heavy lifting" in keyboard controls: responds to a dispatch key.

        Decoupling this into a separate method facillitates giving commands to
        the ListView programmatically, not just through user input,
        and this way makes automation easier.

        :param dispatch_key: A string of the form e.g. ``109+alt,shift``: the ``key``
            number, ``+``, and comma-separated modifiers.

        :returns: True if the dispatch key got handled, False if there is
            no response defined for the given dispatch key.
        """

        if dispatch_key == '8':
            self.remove_from_model()
        elif dispatch_key == '27':
            self.dispatch('on_release')
            self.deselect()
        else:
            return False

        return True

    def on_key_up(self, window, key, scancode, *args, **kwargs):
        # logging.info('EdgeView\t{0}: Handling key_up {1}'.format(self.edge, key))
        return False

    def on_key_captured(self, *largs):
        """Default handler for on_key_captured event."""
        pass

    @staticmethod
    def keypress_to_dispatch_key(key, scancode, codepoint, modifiers):
        """Converts the key_down event data into a single string for more convenient
        keyboard shortcut dispatch."""
        if modifiers:
            return '{0}+{1}'.format(key, ','.join(sorted(modifiers)))
        else:
            return '{0}'.format(key)

    def remove_from_model(self):
        self.remove_bindings()
        self.deselect()
        self.model.ensure_remove_edge(self.start_objid, self.end_objid)
        # Should sync this to model...

    def select(self, *args):
        logging.debug('EdgeView\t{0}: called selection!'.format(self.edge))
        self.background_color = self.selected_color
        if isinstance(self.parent, CompositeListItem):
            self.parent.select_from_child(self, *args)
        super(EdgeView, self).select(*args)
        self.do_render()

    def deselect(self, *args):
        logging.debug('EdgeView\t{0}: called deselection!'.format(self.edge))
        self.background_color = self.deselected_color
        if isinstance(self.parent, CompositeListItem):
            self.parent.deselect_from_child(self, *args)
        super(EdgeView, self).deselect(*args)
        self.do_render()

    def collide_point(self, h, v):
        """The edge collides points only along its course, at most
        self._collide_threshold points away from the line."""
        _m_cthr = self._collide_threshold

        # Cheating to recompute threshold to actual on-screen pixels
        #_cthr = _m_cthr / App.get_running_app()._get_editor_scatter_container_widget().scale
        _cthr = 2   # Nobody really needs to select edges that badly.
                    # We can afford that selecting an edge is frustrating
                    # more than we can afford that selecting the underlying
                    # object is frustrating.
        if not ((self.left - _cthr) <= h <= (self.right + _cthr)
                and (self.bottom - _cthr) <= v <= (self.top + _cthr)):
            return False

        hA = self.horz_start
        vA = self.vert_start
        hB = self.horz_end
        vB = self.vert_end

        # Thanks, Wolfram Alpha!
        norm = (hA - hB) ** 2 + (vA - vB) ** 2
        if norm == 0.0:
            # We are within _cthr
            output = True
        else:
            d_square = old_div((((hA - hB) * (vB - v) - (hB - h) * (vA - vB)) ** 2), norm)
            # logging.warning('EdgeView\t{0}: collision delta_square {1}'.format(self.edge, d_square))
            output = d_square < (_cthr ** 2)

        return output

    def render(self):
        # We are rendering directly onto the EdgeListView's container
        # FloatLayout
        # If the start and end are the same:
        if self._start_and_end_invisibly_close():
            self._adjust_for_invisible_end()

        points = [self.horz_start, self.vert_start,
                  self.horz_end, self.vert_end]

        # logging.debug('EdgeView: Rendering edge {0} with points {1}, selected: {2}'
        #               ''.format(self.edge, points, self.is_selected))
        # logging.info('EdgeView: Derived size {0}, self.size {1}, self.pos {2}'
        #              ''.format((points[0] - points[2], points[1] - points[3]),
        #                        self.size,
        #                        self.pos))
        self.canvas.clear()
        with self.canvas:
            Color(*self.rgb)
            Line(points=points, width=self._line_width)

            # Draw a little square node at the starting point.
            # This one is always red.
            _sns = self._start_node_size
            _delta_start = old_div(_sns, 2.0)
            Color(1, 0, 0)
            Rectangle(pos=(self.horz_start - _delta_start,
                           self.vert_start - _delta_start),
                      size=(_sns, _sns))

            if self.is_selected:
                # logging.info('EdgeView\t{0}: Rendering selected!'.format(self.edge))
                Color(*self.background_color)
                Line(points=points, width=self._selected_line_width)

            # Rectangle(pos=self.pos, size=self.size)

    def do_render(self):
        # logging.info('EdgeView: Requested rendering for edge {0}'
        #              ''.format(self.edge))
        self.render()

    ##########################################################################
    # Touch processing
    def on_touch_down(self, touch):
        """Double-tap selects all edges with the given label.
        This is really slow for Attachments, because there are so many.
        """

        if touch.is_double_tap:
            if self.collide_point(*touch.pos):
                renderer = App.get_running_app().graph_renderer
                renderer.view.select_label(self.label)
                return True

        return super(EdgeView, self).on_touch_down(touch)


class ObjectGraphRenderer(FloatLayout):

    # So far has no capability to handle window/editor rescaling.
    # Maybe fold into CropObjectRenderer?

    views_mask = DictProperty(dict())
    '''If an edge is in the views mask and its entry is False,
    it will not be passed to the adapter for rendering.'''

    redraw = NumericProperty(0)
    '''Change this property to force redraw.'''

    def __init__(self, annot_model, graph, editor_widget, **kwargs):

        super(ObjectGraphRenderer, self).__init__(**kwargs)
        logging.info('ObjectGraphRenderer: initializing, with {0} edges'
                     ' in the graph.'.format(len(graph.edges)))

        self.model = annot_model
        self.graph = graph

        self.size = editor_widget.size
        self.pos = editor_widget.pos

        editor_widget.bind(size=self._update_size)
        editor_widget.bind(pos=self._update_pos)

        self.edge_adapter = DictAdapter(
            data=self.graph.edges,
            args_converter=self.edge_converter,
            selection_mode='multiple',
            cls=EdgeView,
        )

        self.view = EdgeListView(adapter=self.edge_adapter,
                                 size_hint=(None, None),
                                 size=self.size,
                                 pos=self.pos)
        self.edge_adapter.bind(on_selection_change=self.view.broadcast_selection)

        self.views_mask = dict()

        # Hacking the ListView
        # logging.debug('View children: {0}'.format(self.view.children))
        self.view.remove_widget(self.view.children[0])
        self.view.container = FloatLayout(pos=self.pos, size=self.size)
        self.view.add_widget(self.view.container)

        Window.bind(on_key_down=self.view.on_key_down)
        Window.bind(on_key_up=self.view.on_key_up)

        # Automating the redraw pipeline:
        #  - when edge data changes, fill in adapter data,
        self.graph.bind(edges=self.update_edge_adapter_data)
        #  - once adapter data changes, redraw
        self.edge_adapter.bind(data=self.do_redraw)

        self.add_widget(self.view)

    def update_edge_adapter_data(self, instance, edges):
        """Copy the graph's edges to adapter data.

        Also updates the mask.
        """
        self._update_views_mask(edges)

        self.edge_adapter.cached_views = dict()
        new_data = {}

        for e, e_class in edges.items():
            if (e in self.views_mask) and (self.views_mask[e] is False):
                logging.debug('ObjGraphRenderer: edge {0} masked out.'
                             ''.format(e))
                continue
            # The adapter creates its Views from the *values* of
            # its `data` dict. So, we must supply the edge as a part
            # of the dict value, not just the key.
            new_data[e] = (e, e_class)
        # This fires self.do_redraw():
        self.edge_adapter.data = new_data

    def _update_views_mask(self, edges, show_new=True):
        """

        All edges that were previously not in the mask are added,
        with the ``show_new`` argument controlling whether they will
        be shown or hidden by default.

        All edges that were in the mask and are not in the data anymore
        will be removed from the mask.

        All edges that were already in the mask have their status unchanged.
        """
        new_mask = dict()
        for e, e_class in edges.items():
            if e in self.views_mask:
                new_mask[e] = self.views_mask[e]
            else:
                new_mask[e] = show_new
        self.views_mask = new_mask

    def on_redraw(self, instance, pos):
        self.do_redraw()

    def do_redraw(self, *args, **kwargs):
        # Args and kwargs given so that it can be fired by an on_edges
        # event from the graph.
        logging.debug('ObjGraphRenderer: requested do_redraw, renderer'
                     ' size: {0}'
                     ''.format(self.redraw, self.size))
        self.view.populate()
        # self.view.log_rendered_edges()

    def edge_converter(self, row_index, rec):
        """Interface between the edge and the EdgeView."""
        # logging.info('EdgeRenderer: Requesting EdgeView kwargs for edge: {0}'
        #              ''.format(rec))

        e = rec[0]
        e_class = rec[1]

        # Get the connected CropObjects
        obj_from = self.model.cropobjects[e[0]]
        e_obj_from = self._cropobject_to_editor_world(obj_from)

        obj_to = self.model.cropobjects[e[1]]
        e_obj_to = self._cropobject_to_editor_world(obj_to)

        # Return the recomputed objects as kwargs for the EdgeView
        output = {
            'is_selected': False,
            'cropobject_from': e_obj_from,
            'cropobject_to': e_obj_to,
            'edge_label': e_class,
        }
        # logging.info('EdgeRenderer: edge_converter fired, output: {0},'
        #              ' class: {1}'
        #              ''.format(output, self.edge_adapter.get_cls()))
        return output

    def _cropobject_to_editor_world(self, obj):
        """Creates an equivalent of the given CropObject with coordinates
        in the current editor world (uses the App's scaler)."""

        # Recompute a counterpart of theirs to editor world
        mt, ml, mb, mr = obj.bounding_box
        et, el, eb, er = self.scaler.bbox_model2widget(mt, ml, mb, mr)

        obj_updated = copy.deepcopy(obj)
        # Editor world counts X from the *bottom*
        obj_updated.x = eb
        obj_updated.y = el
        obj_updated.width = er - el
        obj_updated.height = et - eb

        return obj_updated

    @property
    def rendered_views(self):
        """The list of actual rendered CropObjectViews that
        the CropObjectListView holds."""
        return [cv for cv in self.view.container.children[:]]

    @property
    def scaler(self):
        return App.get_running_app().image_scaler

    def _update_size(self, instance, size):
        self.size = size
        logging.debug('ObjectGraphRenderer: setting size to {0}'.format(self.size))

    def _update_pos(self, instance, pos):
        self.pos = pos
        logging.debug('ObjectGraphRenderer: setting pos to {0}'.format(self.pos))

    def mask_all(self, label=None):
        if label is None:
            new_mask = {e: False for e in self.graph.edges}
        else:
            new_mask = {}
            for e, l in list(self.graph.edges.items()):
                if l == label:
                    new_mask[e] = False
                else:
                    new_mask[e] = self.views_mask[e]

        self.views_mask = new_mask
        self.update_edge_adapter_data(instance=None,
                                      edges=self.graph.edges)

    def mask(self, edges):
        """Only acts on the given set of edges, doesn't change masking
        for others."""
        new_mask = {e: self.views_mask[e] for e in self.graph.edges}
        for e in edges:
            new_mask[e] = False
        self.views_mask = new_mask
        self.update_edge_adapter_data(instance=None,
                                      edges=self.graph.edges)

    def unmask_all(self, label=None):
        if label is None:
            new_mask = {e: True for e in self.graph.edges}
        else:
            new_mask = {}
            for e, l in list(self.graph.edges.items()):
                if l == label:
                    new_mask[e] = True
                else:
                    new_mask[e] = self.views_mask[e]

        self.views_mask = new_mask
        self.update_edge_adapter_data(instance=None,
                                      edges=self.graph.edges)

    def unmask(self, edges):
        """Only acts on the given set of edges, doesn't change masking
        for others."""
        new_mask = {e: self.views_mask[e] for e in self.graph.edges}
        for e in edges:
            new_mask[e] = True
        self.views_mask = new_mask
        self.update_edge_adapter_data(instance=None,
                                      edges=self.graph.edges)

    def are_all_masked(self, edges=None):
        if edges is None:
            edges = self.graph.edges

        masked = [e for e in edges
                  if ((e in self.views_mask) and (self.views_mask[e] is False))]
        logging.debug('GraphRenderer: {0} masked, {1} total in mask'
                     ''.format(len(masked), len(self.views_mask)))
        output = (len(masked) == len(edges))
        return output


##############################################################################


class EdgeListView(ListView):
    # Needs to implement:
    #  - populate
    #container = FloatLayout()

    @property
    def _model(self):
        return App.get_running_app().annot_model

    @property
    def _graph(self):
        return self._model.graph

    @property
    def rendered_views(self):
        if self.container is None:
            return []
        return self.container.children

    @property
    def selected_views(self):
        return [ev for ev in self.rendered_views if ev.is_selected]

    def broadcast_selection(self, *args, **kwargs):
        """Passes the selection on to the App."""
        def _do_broadcast_selection(*args, **kwargs):
            App.get_running_app().selected_relationships = self.selected_views
        Clock.schedule_once(_do_broadcast_selection)

    def log_rendered_edges(self):
        # logging.info('EdgeListView.log_rendered_edges: self.pos = {0},'
        #              ' self.wpos = {1},'
        #              ' self.size = {2}'.format(self.pos, self.to_window(*self.pos),
        #                                        self.size))
        for e in self.rendered_views:
            logging.debug('EdgeListView.log_rendered_edges: edge {0} with'
                         ' pos {1}, wpos {2}, size {3}'.format(e.edge,
                                                               e.pos,
                                                               e.to_window(*e.pos),
                                                               e.size))

    # Currently a "slow populate": remove everything and then add everything
    def populate(self, istart=None, iend=None):
        logging.info('EdgeListView: populating, with {0}'
                     ' current EdgeViews and {1} edges in adapter.'
                     ''.format(len(self.container.children),
                               len(self.adapter.data)))
        container = self.container

        ###########################
        # The *adapter* represents the "truth" that should be rendered.
        #

        # logging.debug('EdgeListView: populating, container pos={0}, size={1}'
        #               ''.format(container.pos, container.size))

        for w in container.children[:]:
            #logging.debug('EdgeListView.populate: Current edges in container: {0}'
            #              ''.format([ww.edge for ww in container.children]))
            w_key = w.edge
            # if w_key in self._graph.edges:
            if w_key in self.adapter.data:
                continue

            # "Clean up" the EdgeView widget
            w.remove_bindings()
            # Remove from cache
            #logging.info('EdgeListView.populate: Adapter cache {0}'
            #             ''.format(self.adapter.cached_views.keys()))
            w_cache_key = self._adapter_key2index(w_key)
            if (w_cache_key is not None) and (w_cache_key in self.adapter.cached_views):
                # logging.info('Removing edge {0} from adapter cache.'.format(w_key))
                del self.adapter.cached_views[w_cache_key]
            # logging.debug('EdgeListView.populate: Removing edge {0}'.format(w_key))
            container.remove_widget(w)
            self._count -= 1
            # logging.debug('EdgeListView.populate: Finished removing edge {0}'.format(w_key))

        #logging.info('EdgeListView.populate: Edges in container after removal: {0}'
        #             ''.format([ww.edge for ww in container.children]))

        rendered_edges = set([ww.edge for ww in self.container.children[:]])

        # Adapter keys are (from, to), values are True (will be
        # edge classes) -- the adapter is bound to the graph.edges
        # dict.
        for e_key, e in self.adapter.data.items():
            edge, e_label = e  # The adapter has items ((from, to), label)
            if edge in rendered_edges:
                continue
            # logging.info('EdgeListView.populate: Adding edge from adapter {0}'.format(e))
            e_idx = self._adapter_key2index(e_key)
            if e_idx is None:
                raise ValueError('EdgeListView.populate(): Adapter sorted_keys'
                                 ' out of sync with data.')
            item_view = self.adapter.get_view(e_idx)
            # logging.info('EdgeListView.populate: generated EdgeView {0}'.format(item_view.edge))
            ins_index = 0
            container.add_widget(item_view, index=ins_index)
            self._count += 1

        logging.info('EdgeListView: finished populating, with {0}'
                     ' current EdgeViews.'
                     ''.format(len(self.container.children)))

    def _adapter_key2index(self, key):
        """Converts a key into an adapter index, so that we can request
        views based on the keys from the adapter. This avoids having to
        iterate over all the children.

        If the key is not in the adapter, returns None.
        """
        sorted_keys = self.adapter.sorted_keys
        for i, k in enumerate(sorted_keys):
            if k == key:
                return i
        return None

    def on_key_down(self, window, key, scancode, codepoint, modifier):
        logging.debug('EdgeListView.on_key_down(): got keypress {0}'
                      ''.format(key))

    def on_key_up(self, window, key, scancode, *args, **kwargs):
        logging.debug('EdgeListView.on_key_up(): got keypress {0}'
                      ''.format(key))

    def get_edge_view(self, from_objid, to_objid):
        for ev in self.rendered_views:
            e_f, e_t = ev.start_objid, ev.end_objid
            if (e_f, e_t) == (from_objid, to_objid):
                return ev
        return None

    def select_label(self, label):
        """Select all EdgeViews of the given label."""
        for c in self.container.children[:]:
            if c.label == label:
                if c.is_selected is False:
                    c.dispatch('on_release')
            else:
                if c.is_selected is True:
                    c.dispatch('on_release')
