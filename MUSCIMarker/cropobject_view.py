"""This module implements a class that..."""
from __future__ import division
from __future__ import print_function, unicode_literals

import logging
import os
import uuid
from builtins import str

import scipy.misc
from kivy.app import App
from kivy.core.window import Window
from kivy.properties import ListProperty, BooleanProperty, NumericProperty
from kivy.properties import ObjectProperty
from kivy.uix.label import Label
from kivy.uix.listview import SelectableView, CompositeListItem
from kivy.uix.spinner import Spinner
from kivy.uix.togglebutton import ToggleButton
from mung.node import split_cropobject_on_connected_components
from past.utils import old_div

import MUSCIMarker.tracker as tr
from MUSCIMarker.utils import InspectionPopup, keypress_to_dispatch_key

__version__ = "0.0.1"
__author__ = "Jan Hajic jr."


# Should behave like a ToggleButton.
# Important difference from ListItemButton:
#
# * Colors defined at initialization time,
# * Text is empty
class CropObjectView(SelectableView, ToggleButton):
    """The view to an individual MungNode. Implements interface for MungNode
    manipulation.

    Selection
    ---------

    The ``CropObjectView`` is selectable by clicking. Keyboard shortcuts only work
    when the button is selected.

    Mouse interaction
    -----------------

    Once selected, the MungNode can be dragged around [NOT IMPLEMENTED].

    Keyboard shortcuts
    ------------------

    If the CropObjectView handles a key press event, it will not propagate.

    The available keyboard shortcuts are:

    * Backspace: Remove the MungNode
    * Escape: Unselect
    * Arrow keys: move the MungNode by 1 editor-scale pixel.
    * Arrow keys + alt: move the MungNode by 1 display pixel. (Finest.)
    * Arrow keys + shift: stretch the MungNode by 1 editor-scale pixel.
    * Arrow keys + alt + shift: stretch the MungNode by 1 display pixel. (Finest.)
    * i: toggle info label
    * c: change class selection

    """
    selected_color = ListProperty([1., 0., 0., 0.5])
    deselected_color = ListProperty([1., 0., 0., 0.3])

    cropobject = ObjectProperty()

    _info_label_shown = BooleanProperty(False)
    info_label = ObjectProperty(None, allownone=True)

    _mlclass_selection_spinner_shown = BooleanProperty(False)
    mlclass_selection_spinner = ObjectProperty(None, allownone=True)

    _height_scaling_factor = NumericProperty(1.0)
    _width_scaling_factor = NumericProperty(1.0)

    _editor_scale = NumericProperty(1.0)

    def __init__(self, selectable_cropobject, rgb, alpha=0.25, **kwargs):
        """
        :param selectable_cropobject: The intermediate-level MungNode represnetation,
            with recomputed dimension.
        :param rgb:
        :param alpha: Works for deselected color, when selected, multiplied by 1.5
        :param kwargs:
        :return:
        """
        # logging.debug('Render: Initializing CropObjectView with args: c={0},'
        #               ' rgb={1}, alpha={2}'.format(selectable_cropobject, rgb, alpha))
        super(CropObjectView, self).__init__(**kwargs)

        self.text = ''   # We don't want any text showing up

        r, g, b = rgb
        self.selected_color = r, g, b, min([1.0, alpha * 3.0])
        self.deselected_color = r, g, b, alpha
        self.alpha = alpha  # Recorded for future color changes on class change

        # Overriding the default button color and border behavior
        self.background_color = self.deselected_color
        self.background_normal = ''
        self.background_down = ''
        self.border = 0, 0, 0, 0

        # Overriding default release
        self.always_release = False

        self.cropobject = selectable_cropobject
        self.is_selected = selectable_cropobject.is_selected

        # Here, we position the CropObjectView.
        self.size = self.cropobject.width, self.cropobject.height
        self.size_hint = (None, None)
        self.pos = self.cropobject.y, self.cropobject.x

        self._height_scaling_factor = old_div(self.height, float(self._model_counterpart.height))
        self._width_scaling_factor = old_div(self.width, float(self._model_counterpart.width))
        # self.pos_hint = {'x': self.cropobject.x, 'y': self.cropobject.y }
        # self.pos_hint = {'x': 0, 'y': 0 }

        # self.group = self.cropobject.objid

        self._editor_scale = App.get_running_app().editor_scale

        # If the underlying cropobject has a mask, render that mask
        if self._model_counterpart.mask is not None:
            self.render_mask()

        self.register_event_type('on_key_captured')
        self.create_bindings()

    def create_bindings(self):
        # logging.info('Creating bindings for COV {0}'.format(self))
        Window.bind(on_key_down=self.on_key_down)
        Window.bind(on_key_up=self.on_key_up)
        self.bind(pos=self.update_info_label)
        self.bind(size=self.update_info_label)
        self.bind(height=self.update_info_label)
        self.bind(width=self.update_info_label)

        App.get_running_app().bind(editor_scale=self.setter('_editor_scale'))

    def remove_bindings(self):
        # logging.info('Removing bindings for COV {0}'.format(self))
        Window.unbind(on_key_down=self.on_key_down)
        Window.unbind(on_key_up=self.on_key_up)
        self.unbind(pos=self.update_info_label)
        self.unbind(size=self.update_info_label)
        self.unbind(height=self.update_info_label)
        self.unbind(width=self.update_info_label)

        App.get_running_app().unbind(editor_scale=self.setter('_editor_scale'))

    def update_color(self, rgb):
        r, g, b = rgb
        self.selected_color = r, g, b, min([1.0, self.alpha * 3.0])
        self.deselected_color = r, g, b, self.alpha
        if self.is_selected:
            self.background_color = self.selected_color
        else:
            self.background_color = self.deselected_color

    def render_mask(self):
        """NOT IMPLEMENTED

        Rendering a mask in Kivy is difficult. (Can Mesh do nonconvex?)"""
        pass

    ##########################################################################
    # Touch processing
    def on_touch_down(self, touch):

        if touch.is_double_tap:
            if self.collide_point(*touch.pos):
                renderer = App.get_running_app().cropobject_list_renderer
                renderer.view.select_class(self._model_counterpart.clsname)
                return True

        return super(CropObjectView, self).on_touch_down(touch)


    ##########################################################################
    # Keyboard event processing: the core UI of the CropObjectView
    def on_key_down(self, window, key, scancode, codepoint, modifier):
        """This method is one of the primary User Interfaces: keyboard
        shortcuts to manipulate a selected MungNode.

        :param window:
        :param key:
        :param scancode:
        :param codepoint:
        :param modifier:
        :return:
        """
        # if self.cropobject.objid < 50:
        #     logging.info('CropObjectView: Key caught by CropObjectView {0}: {1}'
        #                  ''.format(self,
        #                            (key, scancode, codepoint, modifier)))

        if not self.is_selected:
            return False

        # Get the dispatch key
        # ------------
        dispatch_key = keypress_to_dispatch_key(key, scancode, codepoint, modifier)

        #logging.info('CropObjectView: Handling key {0}, self.is_selected={1},'
        #             ' self.cropobject={2}'
        #             ''.format(dispatch_key, self.is_selected, str(self.cropobject.objid)))

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

        # Deletion
        if dispatch_key == '8':  # Delete
            self.remove_from_model()
        elif dispatch_key == '8+alt': # Delete attachments
            self._model.graph.remove_obj_edges(self.objid)

        # Unselect
        elif dispatch_key == '27':  # Escape
            # logging.info('CropObjectView\t{0}: handling deselect + state to \'normal\''
            #              ''.format(self.objid))
            # Simple deselection is not enough because of the adapter handle_selection()
            # method.
            if self.is_selected:
                self.dispatch('on_release')
            # self.deselect()  # ...called from the adapter's handle_selection()

        # Moving around
        elif dispatch_key == '273':  # Up arrow
            logging.info('CropObjectView: handling move up: DISABLED')
            #self.move(vertical=1)
        elif dispatch_key == '274':  # Down arrow
            logging.info('CropObjectView: handling move down: DISABLED')
            #self.move(vertical=-1)
        elif dispatch_key == '275':  # Right arrow
            logging.info('CropObjectView: handling move right: DISABLED')
            #self.move(horizontal=1)
        elif dispatch_key == '276':  # Left arrow
            logging.info('CropObjectView: handling move left: DISABLED')
            #self.move(horizontal=-1)

        # Fine-grained moving around
        elif dispatch_key == '273+alt':  # Up arrow
            logging.info('CropObjectView: handling move_fine up: DISABLED')
            #self.move_fine(vertical=1)
        elif dispatch_key == '274+alt':  # Down arrow
            logging.info('CropObjectView: handling move_fine down: DISABLED')
            #self.move_fine(vertical=-1)
        elif dispatch_key == '275+alt':  # Right arrow
            logging.info('CropObjectView: handling move_fine right: DISABLED')
            #self.move_fine(horizontal=1)
        elif dispatch_key == '276+alt':  # Left arrow
            logging.info('CropObjectView: handling move_fine left: DISABLED')
            #self.move_fine(horizontal=-1)

        # Coarse-grained stretching
        elif dispatch_key == '273+shift':  # Up arrow
            logging.info('CropObjectView: handling stretch up: DISABLED')
            #self.stretch(vertical=1)
        elif dispatch_key == '274+shift':  # Down arrow
            logging.info('CropObjectView: handling stretch down: DISABLED')
            #self.stretch(vertical=-1)
        elif dispatch_key == '275+shift':  # Right arrow
            logging.info('CropObjectView: handling stretch right: DISABLED')
            #self.stretch(horizontal=1)
        elif dispatch_key == '276+shift':  # Left arrow
            logging.info('CropObjectView: handling stretch left: DISABLED')
            #self.stretch(horizontal=-1)

        # Fine-grained stretching
        elif dispatch_key == '273+alt,shift':  # Up arrow
            logging.info('CropObjectView: handling stretch_fine up: DISABLED')
            #self.stretch_fine(vertical=1)
        elif dispatch_key == '274+alt,shift':  # Down arrow
            logging.info('CropObjectView: handling stretch_fine down: DISABLED')
            #self.stretch_fine(vertical=-1)
        elif dispatch_key == '275+alt,shift':  # Right arrow
            logging.info('CropObjectView: handling stretch_fine right: DISABLED')
            #self.stretch_fine(horizontal=1)
        elif dispatch_key == '276+alt,shift':  # Left arrow
            logging.info('CropObjectView: handling stretch_fine left: DISABLED')
            #self.stretch_fine(horizontal=-1)

        # Change class
        elif dispatch_key == '99':  # c
            logging.info('CropObjectView: handling mlclass selection')
            self.toggle_class_selection()
        elif dispatch_key == '99+shift':
            logging.info('CropObjectView: cloning mlclass to app')
            self.clone_class_to_app()

        # Hide relationships
        elif dispatch_key == '104+alt':  # h
            logging.info('CropObjectView: handling hiding relationships')
            self.toggle_hide_relationships()

        # Inspect MungNodes
        elif dispatch_key == '105':  # i
            logging.info('CropObjectView: handling inspection')
            #self.toggle_info_panel()
            self.inspect()

        elif dispatch_key == '120':  # x
            logging.info('CropObjectView: handling split to connected components')
            self.split()

        else:
            # The key is not recognized by the CropObjectView, try others.
            return False

        # If we got here, the key has been caught and processed.
        # However, maybe we want to do the operation with other selected objects
        # as well.
        # On the other hand: this makes things propagate past the CropObjectViews,
        # so for example Escape unselects all MungNodes *and* quits the application.
        # Therefore, the CropObjectListView should "block" these signals
        # from propagating further.
        # Current policy: if any CropObjectView captures a key signal, it will propagate
        # past the CropObjectListView.
        return True

    def on_key_up(self, window, key, scancode, *args, **kwargs):
        return False

    def on_key_captured(self, *largs):
        """Default handler for on_key_captured event."""
        pass

    # TODO: Remove this (replaced from utils)
    # @staticmethod
    # def keypress_to_dispatch_key(key, scancode, codepoint, modifiers):
    #     """Converts the key_down event data into a single string for more convenient
    #     keyboard shortcut dispatch."""
    #     if modifiers:
    #         return '{0}+{1}'.format(key, ','.join(sorted(modifiers)))
    #     else:
    #         return '{0}'.format(key)

    ##########################################################################
    # Accessing the model & the cropobject in the model, so that the user
    # can manipulate the underlying data through the CropObjectView.
    @property
    def _model(self):
        return App.get_running_app().annot_model

    @property
    def _model_counterpart(self):
        return self._model.cropobjects[self.cropobject.objid]

    @property
    def objid(self):
        return self._model_counterpart.objid

    ##########################################################################
    # Class selection
    @tr.Tracker(track_names=['self'],
                transformations={'self': [lambda s: ('objid', s._model_counterpart.objid),
                                          lambda s: ('clsname', s._model_counterpart.clsname)]},
                fn_name='CropObjectView.toggle_class_selection',
                tracker_name='editing')
    def toggle_class_selection(self):
        if self._mlclass_selection_spinner_shown:
            self.destroy_mlclass_selection_spinner()
        else:
            self.create_class_selection()

    def create_class_selection(self):
        logging.info('CropObjectView\t{0}: show_class_selection() fired.'
                     ''.format(self.cropobject.objid))
        self.mlclass_selection_spinner = Spinner(
            id='mlclass_cropobject_selection_spinner_{0}'.format(self.cropobject.objid),
            pos=self.pos,
            text='{0}'.format(self.cropobject.clsname),
            font_size=15,
            values=sorted(list(self._model.mlclasses_by_name.keys()),
                          key=lambda k: self._model.mlclasses_by_name[k].clsid),
            width=old_div(300, self._editor_scale),
            height=old_div(50, self._editor_scale),
            size_hint=(None, None),
            # is_open=True,
        )
        self.mlclass_selection_spinner.bind(text=self.do_class_selection)
        # self.mlclass_selection_spinner.option_cls.height = 37

        self.add_widget(self.mlclass_selection_spinner)
        self._mlclass_selection_spinner_shown = True

    @tr.Tracker(track_names=['self', 'text'],
                transformations={'self': [lambda s: ('objid', s._model_counterpart.objid),
                                          lambda s: ('clsname', s._model_counterpart.clsname)]},
                fn_name='CropObjectView.do_class_selection',
                tracker_name='editing')
    def do_class_selection(self, spinner_widget, clsname):
        logging.info('CropObjectView\t{0}: do_class_selection() fired.'
                     ''.format(self.cropobject.objid))

        if clsname != self.cropobject.clsname:
            self.set_mlclass(clsname=clsname)
        self.destroy_mlclass_selection_spinner()

    def set_mlclass(self, clsname):
        # This should be wrapped in some cropobject's set_class method.
        self._model_counterpart.clsname = clsname
        self.cropobject.clsname = clsname
        # We should also check that the new class name is consistent
        # with the edges...
        self.update_info_label()

        # Update color
        rgb = tuple([float(x) for x in self._model.mlclasses_by_name[clsname].color])
        self.update_color(rgb)

    def destroy_mlclass_selection_spinner(self, *args, **kwargs):
        self.remove_widget(self.mlclass_selection_spinner)
        self.mlclass_selection_spinner = None
        self._mlclass_selection_spinner_shown = False

    ##########################################################################
    # Info panel: displaying information about the view in the info palette

    def toggle_info_panel(self):
        # Info panel!
        if self._info_label_shown:
            self.destroy_info_label()
        else:
            self.create_info_label()

    def create_info_label(self):
        # logging.debug('CropObjectView.create_info_label() called.')
        info_label = Label(text=self.get_info_label_text())
        _info_palette = App.get_running_app()._get_tool_info_palette()

        info_label.size_hint = (1.0, None)
        info_label.size = (self.parent.size[0], 35)

        self.info_label = info_label
        _info_palette.add_widget(self.info_label)
        self._info_label_shown = True

    def destroy_info_label(self, *args, **kwargs):
        # logging.debug('CropObjectView.destroy_info_label() called.')
        App.get_running_app()._get_tool_info_palette().remove_widget(self.info_label)
        self._info_label_shown = False
        self.info_label = None

    def get_debug_info_label_text(self):
        e_cropobject = self.cropobject
        output_lines = list()
        output_lines.append('objid:            {0}'.format(e_cropobject.objid))
        output_lines.append('cls:                {0}'.format(e_cropobject.clsname))
        output_lines.append('M.x, M.y:      {0:.2f}, {1:.2f}'
                            ''.format(self._model_counterpart.x,
                                      self._model_counterpart.y))
        output_lines.append('M.w, M.h:      {0:.2f}, {1:.2f}'
                            ''.format(self._model_counterpart.width,
                                      self._model_counterpart.height))
        if self._model_counterpart.mask is None:
            output_lines.append('Mask.nnz: None')
        else:
            output_lines.append('Mask.nnz: {0}'.format(self._model_counterpart.mask.sum()))

        output_lines.append('E.x, E.y:        {0:.2f}, {1:.2f}'.format(self.x, self.y))
        output_lines.append('E.w, E.h:        {0:.2f}, {1:.2f}'.format(self.width,
                                                                       self.height))

        output_lines.append('S.V, S.H:       {0:.2f}, {1:.2f}'
                            ''.format(self._height_scaling_factor,
                                      self._width_scaling_factor))
        return '\n'.join(output_lines)

    def get_info_label_text(self):
        c = self._model_counterpart
        text = '({0})  {1}'.format(c.objid, c.clsname)
        if c.data is not None:
            logging.debug('Creating info label for object {0}:'
                          ' data {1}'.format(c.uid, c.data))
            pitch_text = ''
            if 'pitch_step' in c.data:
                pitch_text = '{0}'.format(c.data['pitch_step'])
            elif 'normalized_pitch_step' in c.data:
                pitch_text = '{0}'.format(c.data['normalized_pitch_step'])
            if 'pitch_octave' in c.data:
                pitch_text += '{0}'.format(c.data['pitch_octave'])
            if pitch_text:
                text += ' | {0}'.format(pitch_text)

            if 'duration_beats' in c.data:
                text += ' | {0:.2f}'.format(c.data['duration_beats'])
            if 'onset_beats' in c.data:
                text += ' | {0:.3f}'.format(c.data['onset_beats'])

            # duration_text = None
            # if 'duration_beats' in c.data:
            #     duration_text = '{0:.2f}'.format(c.data['duration_beats'])
            # if duration_text is not None:
            #     text += ' | {0}'.format(duration_text)
        return text

    def update_info_label(self, *args):
        if self.info_label is not None:
            self.info_label.text = self.get_info_label_text()

    ##########################################################################

    def remove_from_model(self):
        logging.info('CropObjectView.remove_from_model(): called on objid {0}'
                     ''.format(self.cropobject.objid))

        # Problem here: the cropobject gets deleted, but the widget stays
        # alive, so it keeps capturing events. This is (a) a memory leak,
        # (b) causes crashes.
        # Easy workaround: unselect self first. This does not fix the memory
        # leak, but at least the 'invisible' CropObjectView will not
        # capture any events.
        self.ensure_deselected()
        # Another workaround: schedule self-deletion for slightly later,
        # after the widget gets removed from the call stack.

        # The problem persists also with widget deletion...
        # After clear()-ing the current CropObjectList, the CropObjectView
        # widgets stay alive!

        # What if the bindings to Window are keeping the widget alive?
        self.remove_bindings()

        # Let's at least deactivate it, so it doesn't do anything.
        # This, however, won't help upon clearing the widgets...
        self.disabled = True
        self._model.remove_cropobject(self.cropobject.objid)

    ##########################################################################
    # Movement & scaling

    @tr.Tracker(track_names=['self', 'vertical', 'horizontal'],
                transformations={'self': [lambda s: ('objid', s._model_counterpart.objid),
                                          lambda s: ('clsname', s._model_counterpart.clsname)]},
                fn_name='CropObjectView.move',
                tracker_name='editing')
    def move(self, vertical=0, horizontal=0):
        """Move the underlying MungNode.

        NOTE: How to deal with MungNodes that have a mask? Roll it?

        In the current implementation, there is no listener inside the model
        for individual MungNodes, so there is no propagation of the change
        to the view. We currently work around this by simply moving the view
        as well, but this will not work when the underlying MungNode is moved
        by some other means.
        """
        logging.info('CropObjectView {0}: moving vertical={1}, horizontal={2}'
                     ''.format(self.cropobject.objid, vertical, horizontal))
        c = self._model_counterpart
        # The MungNodes in the model are kept in the Numpy world.
        c.x += vertical #* self._height_scaling_factor
        c.y += horizontal #* self._height_scaling_factor
        if c.mask is not None:
            logging.warn('CropObjectView {0}: Moving a MungNode invalidates its mask!')
        self._model.add_cropobject(c)

        self.move_view(vertical=vertical, horizontal=horizontal)

    def move_view(self, vertical=0, horizontal=0):
        logging.info('CropObjectView {0}: moving view vertical={1}, horizontal={2}'
                     ''.format(self.cropobject.objid, vertical, horizontal))
        self.pos = (self.pos[0] + horizontal * self._width_scaling_factor,
                    self.pos[1] + vertical * self._width_scaling_factor)

    def move_fine(self, vertical=0, horizontal=0):
        """Move the underlying MungNode.

        In the current implementation, there is no listener inside the model
        for individual MungNodes, so there is no propagation of the change
        to the view. We currently work around this by simply moving the view
        as well, but this will not work when the underlying MungNode is moved
        by some other means.
        """
        logging.info('CropObjectView {0}: moving vertical={1}, horizontal={2}'
                     ''.format(self.cropobject.objid, vertical, horizontal))
        c = self._model_counterpart
        # The MungNodes in the model are kept in the Numpy world.
        c.x += vertical * self._height_scaling_factor / self._editor_scale
        c.y += horizontal * self._height_scaling_factor / self._editor_scale
        self._model.add_cropobject(c)

        self.move_view_fine(vertical=vertical, horizontal=horizontal)

    def move_view_fine(self, vertical=0, horizontal=0):
        logging.info('CropObjectView {0}: moving view vertical={1}, horizontal={2}'
                     ''.format(self.cropobject.objid, vertical, horizontal))
        self.pos = (self.pos[0] + old_div(horizontal, self._editor_scale),# / self._width_scaling_factor),
                    self.pos[1] + old_div(vertical, self._editor_scale))# / self._width_scaling_factor))

    @tr.Tracker(track_names=['self', 'vertical', 'horizontal'],
                transformations={'self': [lambda s: ('objid', s._model_counterpart.objid),
                                          lambda s: ('clsname', s._model_counterpart.clsname)]},
                fn_name='CropObjectView.stretch',
                tracker_name='editing')
    def stretch(self, vertical=0, horizontal=0):
        """Stretch the underlying MungNode. Does NOT change its position.
        Cannot make the MungNode smaller than 1 in either dimension.

        See :meth:`move` for a discussion on linking the model action and view."""
        logging.info('CropObjectView {0}: stretching vertical={1}, horizontal={2}'
                     ''.format(self.cropobject.objid, vertical, horizontal))
        c = self._model_counterpart
        if c.width + horizontal > 0:
            c.width += horizontal #* self._width_scaling_factor
        if c.height + vertical > 0:
            c.height += vertical #* self._height_scaling_factor
        self._model.add_cropobject(c)

        self.stretch_view(vertical=vertical, horizontal=horizontal)

    def stretch_view(self, vertical=0, horizontal=0):
        logging.info('CropObjectView {0}: stretching view vertical={1}, horizontal={2}'
                     ''.format(self.cropobject.objid, vertical, horizontal))
        if self.width + horizontal > 0:
            self.width += horizontal * self._width_scaling_factor
        if self.height + vertical > 0:
            self.height += vertical * self._height_scaling_factor

    def stretch_fine(self, vertical=0, horizontal=0):
        """Stretch the underlying MungNode. Does NOT change its position.
        Cannot make the MungNode smaller than 1 in either dimension.

        See :meth:`move` for a discussion on linking the model action and view."""
        logging.info('CropObjectView {0}: stretching vertical={1}, horizontal={2}'
                     ''.format(self.cropobject.objid, vertical, horizontal))
        c = self._model_counterpart
        if c.width + horizontal > 0:
            c.width += horizontal * self._width_scaling_factor / self._editor_scale
        if c.height + vertical > 0:
            c.height += vertical * self._height_scaling_factor / self._editor_scale
        self._model.add_cropobject(c)

        self.stretch_view_fine(vertical=vertical, horizontal=horizontal)

    def stretch_view_fine(self, vertical=0, horizontal=0):
        logging.info('CropObjectView {0}: stretching view vertical={1}, horizontal={2}'
                     ''.format(self.cropobject.objid, vertical, horizontal))
        if self.width + horizontal > 0:
            self.width += old_div(horizontal, self._editor_scale)# / self._width_scaling_factor)
        if self.height + vertical > 0:
            self.height += old_div(vertical, self._editor_scale)# / self._height_scaling_factor)

    ##########################################################################
    # Split
    @tr.Tracker(track_names=['self', 'ratio'],
                transformations={'self': [lambda s: ('objid', s._model_counterpart.objid),
                                          lambda s: ('clsname', s._model_counterpart.clsname)]},
                fn_name='CropObjectView.split',
                tracker_name='editing')
    def split(self):
        """Split the MungNode according to its mask.
        """
        _next_objid = self._model.get_next_cropobject_id()
        new_cropobjects = split_cropobject_on_connected_components(self._model_counterpart,
                                                                   next_objid=_next_objid)
        if len(new_cropobjects) == 1:
            return

        self.remove_from_model()
        for c in new_cropobjects:
            self._model.add_cropobject(c)


    ##########################################################################
    # Clone class
    @tr.Tracker(track_names=['self'],
                transformations={'self': [lambda s: ('objid', s._model_counterpart.objid),
                                          lambda s: ('clsname', s._model_counterpart.clsname)]},
                fn_name='CropObjectView.clone_class_to_app',
                tracker_name='editing')
    def clone_class_to_app(self):
        App.get_running_app().currently_selected_mlclass_name = self._model_counterpart.clsname


    ##########################################################################
    # Hide relationships
    @tr.Tracker(track_names=['self'],
                transformations={'self': [lambda s: ('objid', s._model_counterpart.objid),
                                          lambda s: ('clsname', s._model_counterpart.clsname),
                                          lambda s: ('inlinks', s._model_counterpart.inlinks),
                                          lambda s: ('outlinks', s._model_counterpart.outlinks)]},

                fn_name='CropObjectView.hide_relationships',
                tracker_name='editing')
    def hide_relationships(self):
        edges = self.collect_all_edges()
        App.get_running_app().graph_renderer.mask(edges)

    @tr.Tracker(track_names=['self'],
                transformations={'self': [lambda s: ('objid', s._model_counterpart.objid),
                                          lambda s: ('clsname', s._model_counterpart.clsname),
                                          lambda s: ('inlinks', s._model_counterpart.inlinks),
                                          lambda s: ('outlinks', s._model_counterpart.outlinks)]},

                fn_name='CropObjectView.hide_relationships',
                tracker_name='editing')
    def show_relationships(self):
        edges = self.collect_all_edges()
        App.get_running_app().graph_renderer.unmask(edges)

    def toggle_hide_relationships(self):
        # A very private toggle switch that keeps track of whether
        # the relationships are hidden or visible.
        graph_renderer = App.get_running_app().graph_renderer
        edges = self.collect_all_edges()
        if graph_renderer.are_all_masked(edges):
            self.show_relationships()
        else:
            self.hide_relationships()

    def collect_all_edges(self):
        edges = []
        for i in self._model_counterpart.inlinks:
            edges.append((i, self.objid))
        for o in self._model_counterpart.outlinks:
            edges.append((self.objid, o))
        return edges



    ##########################################################################
    # Inspect mask
    @tr.Tracker(track_names=['self'],
                transformations={'self': [lambda s: ('objid', s._model_counterpart.objid),
                                          lambda s: ('clsname', s._model_counterpart.clsname)]},
                fn_name='CropObjectView.clone_class_to_app',
                tracker_name='editing')
    def inspect(self):
        """Shows the symbol's exact mask in the context of its bounding box
        in a popup."""
        # Create crop
        image = self._model.image
        crop = self._model_counterpart.project_to(image).astype('float32')
        t, l, b, r = self._model_counterpart.bounding_box
        background_crop = image[t:b, l:r].astype('float32')
        combined_crop = (old_div(crop, 2.0)) + (old_div(background_crop, 2.0))

        # Save image
        app = App.get_running_app()
        tmp_dir = app.tmp_dir
        fname = str(uuid.uuid4()) + '.png'
        full_path = os.path.join(tmp_dir, fname)

        scipy.misc.imsave(full_path, combined_crop, )

        # Make popup with the crop
        data_text = self._model_counterpart.data_display_text()
        popup = InspectionPopup(
            data_text=data_text,
            title='Inspecting obj. {0} | clsname: {1} | bbox: {2}'
                  ''.format(self.objid,
                            self._model_counterpart.clsname,
                            self._model_counterpart.bounding_box)
                  + '\n\n______________________________________\nDATA\n\n' + data_text,
            source=full_path)

        # Bind to delete the temp file on cancel()
        def __safe_unlink(fname):
            if os.path.exists(full_path):
                os.unlink(full_path)

        popup.bind(on_dismiss=lambda x: __safe_unlink(x))
        popup.open()

    ##########################################################################
    # Copied over from ListItemButton
    @tr.Tracker(track_names=['self'],
                transformations={'self': [lambda s: ('objid', s._model_counterpart.objid),
                                          lambda s: ('clsname', s._model_counterpart.clsname)]},
                fn_name='CropObjectView.select',
                tracker_name='editing')
    def select(self, *args):
        # logging.debug('CropObjectView\t{0}: called selection'
        #               ''.format(self.cropobject.objid))
        self.background_color = self.selected_color
        if not self._info_label_shown:
            self.create_info_label()

        if isinstance(self.parent, CompositeListItem):
            self.parent.select_from_child(self, *args)
        super(CropObjectView, self).select(*args)

    @tr.Tracker(track_names=['self'],
                transformations={'self': [lambda s: ('objid', s._model_counterpart.objid),
                                          lambda s: ('clsname', s._model_counterpart.clsname)]},
                fn_name='CropObjectView.deselect',
                tracker_name='editing')
    def deselect(self, *args):
        """Only handles self.is_selected, not the 'on_release'
        dispatch that the ListAdapter uses to maintain selection!
        Use ensure_deselected() instead."""
        # logging.debug('CropObjectView\t{0}: called deselection'
        #               ''.format(self.cropobject.objid))
        # logging.debug('CropObjectView.deselect: info label shown? {0}'
        #               ''.format(self._info_label_shown))
        if self._info_label_shown:
            # logging.debug('CropObjectView.deselect: destroying info label.')
            self.destroy_info_label()
        if self._mlclass_selection_spinner_shown:
            self.destroy_mlclass_selection_spinner()

        self.background_color = self.deselected_color

        if isinstance(self.parent, CompositeListItem):
            self.parent.deselect_from_child(self, *args)
        super(CropObjectView, self).deselect(*args)

    # def do_deselect(self):
    #     """Proper deselection that will be reflected in a ListAdapter
    #     containing this view."""
    #     if self.is_selected:
    #         self.dispatch('do_release')

    def ensure_selected(self):
        """Proper selection that will be reflected in a ListAdapter
        containing this view."""
        if not self.is_selected:
            self.dispatch('on_release')

    def ensure_deselected(self):
        """Proper unselection that will be reflected in a ListAdapter
        containing this view."""
        if self.is_selected:
            self.dispatch('on_release')

    def select_from_composite(self, *args):
        self.background_color = self.selected_color

    def deselect_from_composite(self, *args):
        self.background_color = self.deselected_color

    # For logging/debugging multi-selection only.
    #
    # def on_is_selected(self, instance, pos):
    #     logging.info('CropObjectView\t{0}: is_selected changed to {1}'
    #                  ''.format(self.cropobject.objid, self.is_selected))
    #
    # def on_press(self):
    #     logging.info('CropObjectView.on_press()\t{0}: Fired'
    #                  ''.format(self.cropobject.objid))
    #     return super(CropObjectView, self).on_press()
    #
    # def on_release(self):
    #     logging.info('CropObjectView.on_release()\t{0}: Fired'
    #                  ''.format(self.cropobject.objid))
    #     return super(CropObjectView, self).on_release()
    #
    # def on_touch_up(self, touch):
    #     if touch.grab_current is not self:
    #         logging.info('CropObjectView.on_touch_up()\t{0}: touch {1} is FOREIGN'
    #                      ''.format(self.cropobject.objid, touch))
    #     else:
    #         logging.info('CropObjectView.on_touch_up()\t{0}: touch {1} is MINE'
    #                      ''.format(self.cropobject.objid, touch))
    #     return super(CropObjectView, self).on_touch_up(touch)
