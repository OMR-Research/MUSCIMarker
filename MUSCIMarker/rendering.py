"""This module implements a class that..."""
from __future__ import print_function, unicode_literals
from __future__ import division

from builtins import map
from builtins import zip
from builtins import str
from builtins import range
from past.utils import old_div
import collections
import copy
import logging

# import gc

from kivy.adapters.dictadapter import DictAdapter
from kivy.adapters.simplelistadapter import SimpleListAdapter
from kivy.app import App
from kivy.compat import PY2
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import DictProperty, ObjectProperty, ListProperty, NumericProperty, BooleanProperty, AliasProperty
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.listview import ListItemButton, ListView, SelectableView, ListItemReprMixin, CompositeListItem
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

from MUSCIMarker.cropobject_view import CropObjectView
from muscima.inference import InferenceEngineConstants as _CONST
from muscima.cropobject import cropobjects_merge_bbox, cropobjects_merge_mask, cropobjects_merge_links
import MUSCIMarker.tracker as tr
from MUSCIMarker.utils import keypress_to_dispatch_key

__version__ = "0.0.1"
__author__ = "Jan Hajic jr."

Builder.load_string('''
<CropObjectListView@ListView>:
    container: container
    # RelativeLayout:
    FloatLayout:
        id: container
        pos: root.pos
        size_hint: 1, 1
''')


class CropObjectListView(ListView):
    """Container for the CropObjectViews of the annotated CropObjects.

    Important behaivors:

    Selection
    ---------

    The adapter initialized in CropObjectRenderer has selection behavior
    set to ``multiple``.

    Keyboard event trapping
    ------------------------

    Because of multiple selection, keyboard shortcuts may affect multiple
    CropObjectViews and therefore should not get trapped by the individual
    views. However, if the keyboard event is handled by a CropObjectView,
    it should not propagate beyond the CropObjectListView -- the event
    has already been handled. (For instance, if the CropObjectListView
    did not catch the 'escape' key, the application shuts down.) Therefore,
    CropObjectListView implements keyboard event trapping, shielding
    the rest of the application from keyboard events handled by
    CropObjectViews.

    The CropObjectViews implement a ``on_key_captured`` event that fires
    when the View handles to a keyboard shortcut. In :meth:`populate()`,
    the CropObjectListView binds its ``_key_trap`` setter to this event.
    Whenever a child CropObjectView fires a key, the ``_key_trap`` property
    of the CropObjectListView is set to ``True``.

    Then, the CropObjectListView implements its own :meth:`on_key_down`
    and :meth:`on_key_up` methods, which check the value of ``_key_trap``
    (through :meth:`_handle_key_trap`) and if the trap is set, unset it
    and return ``True`` to stop the keyboard event from propagating further.

    Because the keyboard events are first handled in all the CropObjectViews
    and only then in their containing CropObjectListView, when multiple
    CropObjectViews are selected, the trap will be set many times through
    all the ``on_key_captured`` events, but only sprung once, when the
    event bubbles to the CropObjectListView.
    """
    # This will be the difficult part...

    _rendered_objids = DictProperty()
    '''Keep track of which CropObjects have already been rendered.
    [NOT IMPLEMENTED]'''

    _trap_key = BooleanProperty(False)

    render_new_to_back = BooleanProperty(False)
    '''If True, will send new CropObjectsViews to the back of the container
    instead of on top when populating.'''

    render_staff_to_back = BooleanProperty(True)
    '''If True, will send new CropObjectViews whose class is a staff object
    (staff_line, staff_space, or staff) to the back of the container instead
    of on top when populating. This means that staff objects will not
    obscure other objects on click.'''

    @property
    def _model(self):
        return App.get_running_app().annot_model

    def populate(self, istart=None, iend=None):

        logging.info('CropObjectListView.populate(): started')
        logging.info('CropObjectListView.populate(): selection size: {0}'
                     ''.format(len(self.adapter.selection)))
        container = self.container

        widgets_rendered = {}
        # Index widgets for removal. Removal is scheduled from the current
        # widgets (CropObjectViews), which are at this point out of sync
        # with the adapter data.
        widgets_for_removal = {}
        for w in container.children:
            w_objid = w.cropobject.objid
            widgets_rendered[w_objid] = w
            if w_objid not in self.adapter.data:
                widgets_for_removal[w_objid] = w

        logging.info('CropObjectListView.populate(): will remove {0} widgets'
                     ''.format(len(widgets_for_removal)))

        # Remove widgets for removal.
        for w_objid, w in widgets_for_removal.items():
            # Deactivate bindings, to prevent widget immortality
            w.remove_bindings()
            # Also remove widget from adapter cache.
            # If they are in the cache, it means either:
            #  - They are stale and need to be removed; in case the incoming
            #    CropObjects have the same objid as one of the removed
            #    cropobjects, it would cause the cache to retrieve the already
            #    deleted CropObjectView.
            #  - The new data in the adapter with these objids has already
            #    been converted to a CropObjectView from somewhere. In that
            #    case, removing it from the cache is slightly inefficient,
            #    but does not hurt correctness.
            w_idx = self._adapter_key2index(w_objid)
            if (w_idx is not None) and (w_idx in self.adapter.cached_views):
                del self.adapter.cached_views[w_idx]
            container.remove_widget(w)
            self._count -= 1

        # Index cropobjects to add.
        # These are drawn from the adapter data, which are at this point
        # out of sync with the container widgets (CropObjectViews).
        cropobjects_to_add = {}
        for c_objid, c in self.adapter.data.items():
            if c_objid not in widgets_rendered:
                cropobjects_to_add[c_objid] = c

        logging.info('CropObjectListView.populate(): will add {0} widgets'
                     ''.format(len(cropobjects_to_add)))

        # Add cropobjects to add.
        for c_objid, c in cropobjects_to_add.items():
            c_idx = self._adapter_key2index(c_objid)
            # Because the cropobjects_to_add are derived from current adapter data,
            # the corresponding keys should definitely be there. But just in case,
            # we check.
            if c_idx is None:
                raise ValueError('CropObjectListView.populate(): Adapter sorted_keys'
                                 ' out of sync with data.')
            item_view = self.adapter.get_view(c_idx)
            # logging.debug('Populating with view that has color {0}'
            #               ''.format(item_view.selected_color))
            # See CropObjectListView key trapping below.
            item_view.bind(on_key_captured=self.set_key_trap)

            # Do new objects go into the back, or into the front?
            if self.render_new_to_back:
                ins_index = len(container.children)
            elif self.render_staff_to_back \
                 and (c.clsname in _CONST.STAFF_CROPOBJECT_CLSNAMES):
                ins_index = len(container.children)
            else:
                ins_index = 0
            container.add_widget(item_view, index=ins_index)
            self._count += 1

        #logging.info('CropObjectListView.populate(): finished, available'
        #             ' CropObjects: {0}'.format([c.objid for c in self.rendered_views]))
        logging.info('CropObjectListView.populate(): selection size: {0}'
                     ''.format(len(self.adapter.selection)))

    @property
    def rendered_views(self):
        """The list of actual rendered CropObjectViews that
        the CropObjectListView holds."""
        if self.container is None:
            return []
        return [cv for cv in self.container.children[:]]

    @property
    def selected_views(self):
        return [cv for cv in self.rendered_views if cv.is_selected]

    def broadcast_selection(self, *args, **kwargs):
        """Passes the selection on to the App."""
        def _do_broadcast_selection(*args, **kwargs):
            App.get_running_app().selected_cropobjects = self.selected_views
        Clock.schedule_once(_do_broadcast_selection)

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

    #########################################################################
    # Handling mass selection/deselection

    def unselect_all(self):
        container = self.container
        for w in container.children[:]:
            # This binds to the adapter's handle_selection
            w.ensure_deselected()
            #if w.is_selected is True:
            #    w.dispatch('on_release')
            #w.deselect()
            #if hasattr(w, 'is_selected'):
            #    w.is_selected = False

    def select_class(self, clsname):
        """Select all CropObjects of the given class."""
        for c in self.container.children[:]:
            if c._model_counterpart.clsname == clsname:
                if c.is_selected is False:
                    c.dispatch('on_release')
            else:
                if c.is_selected is True:
                    c.dispatch('on_release')

    def ensure_selected_objids(self, objids):
        """Mass selection of the given list of ``objids``.

        Fails with KeyError if an invalid objid is given."""
        for objid in objids:
            self.get_cropobject_view(objid).ensure_selected()

    def sync_selection_with_adapter(self, *args, **kwargs):
        """Make sure that the selection state in the adapter is reflected
        in the selection state of the CropObjectViews themselves.

        Note
        ----

        Implemented to fix a bug when mass-deletion of CropObjects did not
        properly call deselect(), whcih manifested itself as undestructible
        info labels.
        """
        # logging.warn('CropObjectViewList: sync selection state: {0}'.format(self.adapter.selection))
        for cv in self.rendered_views:
            if cv in self.adapter.selection:
                # if cv.is_selected:
                #     logging.warn('CropObjectViewList: Out of sync adapter.selection and view.is_selected: object {0}'
                #                  ''.format(cv.cropobject.objid))
                #     continue
                cv.ensure_selected()
            else:
                # if not cv.is_selected:
                #     logging.warn('CropObjectViewList: Out of sync adapter.selection and view.is_selected: object {0}'
                #                  ''.format(cv.cropobject.objid))
                #     continue
                cv.ensure_deselected()

    ##########################################################################
    # Keyboard event trapping
    #  - If a child view captures an on_key_down (event on_key_captured),
    #    will set a trap for on_key_down events bubbling up.
    #    All children will react to the event before the ListView,
    #    so the trap will simply be set many times.
    #  - Then, when the CropObjectViews have finished handling the
    #    on_key_down event and it bubbles up to the ListView, if the trap
    #    is set, the event is captured and doesn't bubble further up.
    # This strategy means one keystroke applies to all selected CropObjects.
    def handle_key_trap(self, *args):
        logging.debug('CropObjectListView: handling key trap in state {0}'
                      ''.format(self._trap_key))
        if self._trap_key:
            self._trap_key = False
            logging.debug('CropObjectListView: trapped key event {0}'
                          ''.format(args))
            return True
        return False

    def set_key_trap(self, *largs):
        logging.debug('CropObjectListView.set_key_trap(): Got args {0}'
                      ''.format(largs))
        self._trap_key = True

    def on_key_down(self, window, key, scancode, codepoint, modifier):
        logging.debug('CropObjectListView.on_key_down(): trap {0}'
                      ''.format(self._trap_key))
        if self.handle_key_trap(window, key, scancode, codepoint, modifier):
            logging.debug('CropObjectListView: NOT propagating keypress')
            return True

        dispatch_key = keypress_to_dispatch_key(key, scancode, codepoint, modifier)

        is_handled = self.handle_dispatch_key(dispatch_key)
        return is_handled

    def handle_dispatch_key(self, dispatch_key):
        """Does the "heavy lifting" in keyboard controls of the CropObjectListView:
        responds to a dispatch key.

        Decoupling this into a separate method facillitates giving commands to
        the ListView programmatically, not just through user input,
        and this way makes automation easier.

        :param dispatch_key: A string of the form e.g. ``109+alt,shift``: the ``key``
            number, ``+``, and comma-separated modifiers.

        :returns: True if the dispatch key got handled, False if there is
            no response defined for the given dispatch key.
        """

        # Keyboard shortcuts that affect the current selection:

        # M for merge
        if dispatch_key == '109':
            logging.info('CropObjectListView: handling merge')
            self.merge_current_selection(destructive=True)
        # M+shift for non-destrcutive merge
        if dispatch_key == '109+shift':
            logging.info('CropObjectListView: handling non-destructive merge')
            # We need to remember the selection, because the merge updates
            # the adapter data, and on a data update, the adapter forgets
            # its selection. So after the merge, the parser wouldn't see
            # anything selected.
            # We know the merge is non-destructive, so we can count on these
            # model CropObjects to exist after the merge as well as now.
            _selected_cropobjects = [copy.deepcopy(v._model_counterpart)
                                     for v in self.adapter.selection]
            c = self.merge_current_selection(destructive=False, deselect=True)
            # Now we can parse.
            # We need to add the new CropObject to the parsing inputs, though:
            # otherwise, of course the parser wouldn't find its edges.
            self._parse_cropobjects(_selected_cropobjects + [c])
            self.unselect_all()
        # B for sending selection to back (for clickability)
        if dispatch_key == '98':
            logging.info('CropObjectListView: sending selected CropObjects'
                         ' to the back of the view stack.')
            self.send_current_selection_back()

        # C+shift+ctrl to apply current class to selection
        if dispatch_key == '99+ctrl,shift':
            logging.info('CropObjectListView: applying current MLClass to '
                         'selection.')
            clsname = App.get_running_app().currently_selected_mlclass_name
            self.apply_mlclass_to_selection(
                clsid=self._model.mlclasses_by_name[clsname].clsid,
                clsname=clsname
            )

        # A for attaching
        if dispatch_key == '97':
            logging.info('CropObjectListView: attaching selected CropObjects.')
            self.process_attach()
        # D for detaching
        if dispatch_key == '100':
            logging.info('CropObjectListView: detaching selected CropObjects.')
            self.process_detach()

        # alt+h for global hide relationships
        if dispatch_key == '104+alt':
            logging.info('CropObjectListView: hiding all relationships.')
            self.process_hide_relationships()

        # P for actual parsing
        if dispatch_key == '112':
            logging.info('CropObjectListView: handling parse with deterministic parser')
            self.parse_current_selection(unselect_at_end=True, backup=True)

        if dispatch_key == '112+shift':
            logging.info('CropObjectListView: handling parse with probabilistic parser')
            self.parse_current_selection(unselect_at_end=True, backup=False)


        # N for precedence edge inference
        if dispatch_key == '110':
            logging.info('CropObjectListView: handling precedence parse,'
                         'IS factored by staff')
            self.infer_precedence_for_current_selection(unselect_at_end=True,
                                                        factor_by_staff=True)
        # Shift+N for precedence edge inference
        if dispatch_key == '110+shift':
            logging.info('CropObjectListView: handling precedence parse, '
                         'NOT factored by staff')
            self.infer_precedence_for_current_selection(unselect_at_end=True,
                                                        factor_by_staff=False)
        # Alt+Shift+N for simultaneity edge inference (relies on MIDI being built)
        if dispatch_key == '110+alt,shift':
            logging.info('CropObjectListView: handling simultaneity parse')
            self.infer_simultaneity_for_current_selection(unselect_at_end=True)
        # Ctrl+Alt+Shift+N for simultaneity edge inference (relies on MIDI being built)
        if dispatch_key == '110+alt,ctrl,shift':
            logging.info('CropObjectListView: handling simultaneity parse')
            self.remove_simultaneity_for_current_selection(unselect_at_end=True)

        # S for merging all stafflines
        if dispatch_key == '115+shift':
            logging.info('CropObjectListView: handling staffline merge')
            self.process_stafflines(build_staffs=True,
                                    build_staffspaces=True,
                                    add_staff_relationships=True)

        else:
            logging.info('CropObjectListView: propagating keypress')
            return False

        # Things caught in the CropObjectListView do not propagate.
        #logging.info('CropObjectListView: NOT propagating keypress')
        return True

    def on_key_up(self, window, key, scancode, *args, **kwargs):
        logging.debug('CropObjectListView.on_key_up(): trap {0}'
                     ''.format(self._trap_key))
        if self.handle_key_trap(window, key, scancode):
            logging.debug('CropObjectListView: NOT propagating keypress')
            return True

    ##########################################################################
    # Operations on lists of selected CropObjects
    def process_attach(self):
        cropobjects = [s._model_counterpart for s in self.adapter.selection]
        if len(cropobjects) != 2:
            logging.warn('Currently cannot process attachment for a different'
                         ' number of selected CropObjects than 2.')
            return

        a1, a2 = cropobjects[0].objid, cropobjects[1].objid
        self._model.ensure_add_edge((a1, a2))

    def process_detach(self):
        cropobjects = [s._model_counterpart for s in self.adapter.selection]
        if len(cropobjects) != 2:
            logging.warn('Currently cannot process attachment for a different'
                         ' number of selected CropObjects than 2.')
            return

        a1, a2 = cropobjects[0].objid, cropobjects[1].objid
        self._model.graph.ensure_remove_edge(a1, a2)

    def process_hide_relationships(self):
        graph_renderer = App.get_running_app().graph_renderer
        if len(self.adapter.selection) == 0:
            if not graph_renderer.are_all_masked():
                graph_renderer.mask_all()
            else:
                graph_renderer.unmask_all()
        else:
            edges = []
            for v in self.adapter.selection:
                e = v.collect_all_edges()
                edges.extend(e)
            edges = list(set(edges)) # Get unique
            if not graph_renderer.are_all_masked(edges=edges):
                graph_renderer.mask(edges=edges)
            else:
                graph_renderer.unmask(edges=edges)

    def send_current_selection_back(self):
        """Moves the selected items back in the rendering order,
        so that if they obscure other items, these obscured items
        will become clickable."""
        logging.info('CropObjectListView.back(): selection {0}'
                     ''.format(self.adapter.selection))
        if len(self.adapter.selection) == 0:
            logging.warn('CropObjectListView.back(): trying to send back empty'
                         ' selection.')
            return

        # How to achieve sending them back?
        # The selected CropObjectView needs to become a new child.
        #cropobjects = [s._model_counterpart for s in self.adapter.selection]

        for s in self.adapter.selection:
            # Remove from children and add to children end
            self.container.remove_widget(s)
            self.container.add_widget(s, index=len(self.container.children[:]))
            #s.remove_from_model()

        #self.render_new_to_back = True
        #for c in cropobjects:
        #    App.get_running_app().annot_model.add_cropobject(c)
        #self.render_new_to_back = False

    def merge_current_selection(self, destructive=True, deselect=True):
        """Take all the selected items and merge them into one.
        Uses the current MLClass.

        :param destructive: If set to True, will remove the selected
            CropObjects from the model. If False, will only unselect
            them.

        :returns: The newly created CropObject.
        """
        logging.info('CropObjectListView.merge(): selection {0}'
                     ''.format(self.adapter.selection))
        if len(self.adapter.selection) == 0:
            logging.warn('CropObjectListView.merge(): trying to merge empty selection.')
            return

        model_cropobjects = [c._model_counterpart for c in self.adapter.selection]
        t, l, b, r = cropobjects_merge_bbox(model_cropobjects)
        mask = cropobjects_merge_mask(model_cropobjects)
        inlinks, outlinks = cropobjects_merge_links(model_cropobjects)

        # Remove the merged CropObjects
        # logging.info('CropObjectListView.merge(): inlinks {0}, outlinks {1}'
        #              ''.format(inlinks, outlinks))
        logging.info('CropObjectListView.merge(): Removing/deselecting selection {0}'
                     ''.format([c.objid for c in self.adapter.selection]))
        if destructive:
            to_destroy = [s for s in self.adapter.selection]
            for s in to_destroy:
                logging.info('CropObjectListView.merge(): Destroying {0}'
                             ''.format(s._model_counterpart.uid))
                s.remove_from_model()
            # for s in self.adapter.selection:
            #     logging.info('CropObjectListView.merge(): removing {0}'
            #                  ''.format(s._model_counterpart.uid))
            #     logging.info('CropObjectListView.merge(): Before removal,'
            #                  ' selection: {0}'.format(self.adapter.selection))
            #     s.remove_from_model()
            #     logging.info('CropObjectListView.merge(): After removal,'
            #                  ' selection: {0}'.format(self.adapter.selection))
        elif deselect:
            self.unselect_all()

        model_cropobjects = None  # Release refs

        self.render_new_to_back = True
        c = App.get_running_app().generate_cropobject_from_model_selection({'top': t,
                                                                            'left': l,
                                                                            'bottom': b,
                                                                            'right': r},
                                                                           mask=mask)
        c.inlinks = inlinks
        c.outlinks = outlinks

        self._model.add_cropobject(c)
        # Problem with retaining selection: this triggers repopulation
        self.render_new_to_back = False

        return c

    def apply_mlclass_to_selection(self, clsid, clsname):
        for s in self.adapter.selection:
            s.set_mlclass(clsname=clsname)

    @tr.Tracker(track_names=['self'],
                transformations={'self': [
                    lambda v: ('objids', [c.objid for c in v.selected_views]),
                    lambda v: ('mlclass_names', [c._model_counterpart.clsname
                                                 for c in v.selected_views])
                ]
                },
                fn_name='CropObjectListView.parse_current_selection',
                tracker_name='model')
    def parse_current_selection(self, unselect_at_end=True, backup=True):
        """Adds edges among the current selection according to the model's
        grammar and parser. If nothing is selected, parses everything."""
        cropobjects = [s._model_counterpart for s in self.adapter.selection]
        if len(cropobjects) == 0:
            cropobjects = [s._model_counterpart for s in self.container.children]
        self._parse_cropobjects(cropobjects, backup=backup)

        if unselect_at_end:
            self.unselect_all()

    def _parse_cropobjects(self, cropobjects, backup=True):
        """Adds edges among the given cropobjects according to the model's
        grammar and parser."""
        logging.info('CropObjectListView.parse_selection(): {0} cropobjects'
                     ''.format(len(cropobjects)))

        if backup:
            parser = self._model.backup_parser
        else:
            parser = self._model.parser

        if parser is None:
            logging.info('CropObjectListView.parse_selection(): No parser found!')
            return

        # names = [c.clsname for c in cropobjects]
        non_staff_cropobjects = [c for c in cropobjects
                                 if c.clsname not in \
                                 _CONST.STAFF_CROPOBJECT_CLSNAMES]
        edges = parser.parse(non_staff_cropobjects)
        #edges = [(cropobjects[i].objid, cropobjects[j].objid)
        #         for i, j in edges_idxs]
        logging.info('CropObjectListView.parse_selection(): {0} edges to add'
                     ''.format(len(edges)))

        #self._model.graph.ensure_add_edges(edges)
        self._model.ensure_add_edges(edges, label='Attachment')

    @tr.Tracker(track_names=['self'],
                transformations={'self': [
                    lambda v: ('objids', [c.objid for c in v.selected_views]),
                    lambda v: ('mlclass_names', [c._model_counterpart.clsname
                                                 for c in v.selected_views])
                ]
                },
                fn_name='CropObjectListView.infer_precedence_for_current_selection',
                tracker_name='model')
    def infer_precedence_for_current_selection(self,
                                               unselect_at_end=True,
                                               factor_by_staff=False):
        """Adds edges among the current selection according to the model's
        grammar and parser."""
        cropobjects = [s._model_counterpart for s in self.adapter.selection]
        if len(cropobjects) == 0:
            cropobjects = list(self._model.cropobjects.values())

        # Find staffs also as children of selected objects!
        # Their staff might be ignored in the selection.
        related_staffs = self._model.find_related_staffs(cropobjects)
        _cdict = {c.objid: c for c in cropobjects}
        new_related_staffs = [s for s in related_staffs if s.objid not in _cdict]
        logging.info('Infer_precedence_for_current_selection(): found'
                     ' {0} related staff objects, of which {1} are not in selection.'
                     ''.format(len(related_staffs), len(new_related_staffs)))
        cropobjects = cropobjects + new_related_staffs
        logging.info('Infer_precedence_for_current_selection(): had {0}'
                     ' objects, with related stafflines: {1} objects'
                     ''.format(len(_cdict), len(cropobjects)))

        self._infer_precedence(cropobjects, factor_by_staff=factor_by_staff)

        if unselect_at_end:
            self.unselect_all()

    def _infer_precedence(self, cropobjects, factor_by_staff=False):

        _relevant_clsnames = set(list(_CONST.NONGRACE_NOTEHEAD_CLSNAMES)
                                 + list(_CONST.REST_CLSNAMES))
        prec_cropobjects = [c for c in cropobjects
                            if c.clsname in _relevant_clsnames]
        logging.info('_infer_precedence: {0} total prec. cropobjects'
                     ''.format(len(prec_cropobjects)))

        # Group the objects according to the staff they are related to
        # and infer precedence on these subgroups.
        if factor_by_staff:
            staffs = [c for c in cropobjects
                      if c.clsname == _CONST.STAFF_CLSNAME]
            logging.info('_infer_precedence: got {0} staffs'.format(len(staffs)))
            staff_objids = {c.objid: i for i, c in enumerate(staffs)}
            prec_cropobjects_per_staff = [[] for _ in staffs]
            # All CropObjects relevant for precedence have a relationship
            # to a staff.
            for c in prec_cropobjects:
                for o in c.outlinks:
                    if o in staff_objids:
                        prec_cropobjects_per_staff[staff_objids[o]].append(c)

            logging.info('Precedence groups: {0}'
                         ''.format(prec_cropobjects_per_staff))
            for prec_cropobjects_group in prec_cropobjects_per_staff:
                self._infer_precedence(prec_cropobjects_group,
                                       factor_by_staff=False)
            return

        if len(prec_cropobjects) <= 1:
            logging.info('EdgeListView._infer_precedence: less than 2'
                         ' timed CropObjects selected, no precedence'
                         ' edges to infer.')
            return

        # Group into equivalence if noteheads share stems
        _stems_to_noteheads_map = collections.defaultdict(list)
        for c in prec_cropobjects:
            for o in c.outlinks:
                c_o = self._model.cropobjects[o]
                if c_o.clsname == 'stem':
                    _stems_to_noteheads_map[c_o.objid].append(c.objid)

        _prec_equiv_objids = []
        _stemmed_noteheads_objids = []
        for _stem_objid, _stem_notehead_objids in list(_stems_to_noteheads_map.items()):
            _stemmed_noteheads_objids = _stemmed_noteheads_objids \
                                        + _stem_notehead_objids
            _prec_equiv_objids.append(_stem_notehead_objids)
        for c in prec_cropobjects:
            if c.objid not in _stemmed_noteheads_objids:
                _prec_equiv_objids.append([c.objid])

        equiv_objs = [[self._model.cropobjects[objid] for objid in equiv_objids]
                      for equiv_objids in _prec_equiv_objids]

        # Order the equivalence classes left to right
        sorted_equiv_objs = sorted(equiv_objs,
                                   key=lambda eo: min([o.left for o in eo]))

        edges = []
        for i in range(len(sorted_equiv_objs) - 1):
            fr_objs = sorted_equiv_objs[i]
            to_objs = sorted_equiv_objs[i+1]
            for f in fr_objs:
                for t in to_objs:
                    edges.append((f.objid, t.objid))

        self._model.ensure_add_edges(edges, label='Precedence')

    @tr.Tracker(track_names=['self'],
                transformations={'self': [
                    lambda v: ('objids', [c.objid for c in v.selected_views]),
                    lambda v: ('mlclass_names', [c._model_counterpart.clsname
                                                 for c in v.selected_views])
                ]
                },
                fn_name='CropObjectListView.infer_simultaneity_for_current_selection',
                tracker_name='model')
    def infer_simultaneity_for_current_selection(self,
                                                 unselect_at_end=True):
        """Adds simultaneity edges between objects that have the same onset.
        For readability, does not add the complete graph, but just links
        the objects top-down. (Simultaneity is non-oriented, but this is the
        way it works for now.)"""
        cropobjects = [s._model_counterpart for s in self.adapter.selection]
        if len(cropobjects) == 0:
            cropobjects = list(self._model.cropobjects.values())

        objects_with_onset = [c for c in cropobjects
                              if (c.data is not None) and ('onset_beats' in c.data)]
        onsets_dict = collections.defaultdict(list)
        for c in objects_with_onset:
            onsets_dict[c.data['onset_beats']].append(c)

        edges = []
        for o in onsets_dict:
            cgroup = sorted(onsets_dict[o], key=lambda x: old_div((x.top + x.bottom), 2.))
            if len(cgroup) > 1:
                for f, t in zip(cgroup[:-1], cgroup[1:]):
                    edges.append((f.objid, t.objid))

        self._model.ensure_add_edges(edges, label='Simultaneity')

    def remove_simultaneity_for_current_selection(self,
                                                  unselect_at_end=True):
        """Remove simultaneity edges from selection (or all,
        if nothing is selected).
        """
        cropobjects = [s._model_counterpart for s in self.adapter.selection]
        if len(cropobjects) == 0:
            cropobjects = list(self._model.cropobjects.values())

        self._model.clear_relationships(label='Simultaneity',
                                        cropobjects=cropobjects)

    def get_cropobject_view(self, objid):
        """Retrieves the CropObjectView based on the objid. Useful e.g.
        for programmatic selection/deselection of individual objects.

        If the View for the given objid is not rendered, raises a KeyError."""
        for v in self.rendered_views:
            if v.objid == objid:
                return v

        raise KeyError('CropObjectView with objid {0} not found among rendered'
                       ' CropObjects.'.format(objid))

    @tr.Tracker(track_names=['self'],
                transformations={'self': [
                    lambda v: ('objids', [c.objid for c in v.selected_views]),
                    lambda v: ('mlclass_names', [c._model_counterpart.clsname
                                                 for c in v.selected_views])
                ]
                },
                fn_name='CropObjectListView.merge_all_stafflines',
                tracker_name='model')
    def process_stafflines(self,
                           build_staffs=False,
                           build_staffspaces=False,
                           add_staff_relationships=False):
        self._model.process_stafflines(build_staffs=build_staffs,
                                       build_staffspaces=build_staffspaces,
                                       add_staff_relationships=add_staff_relationships)

##############################################################################


class CropObjectRenderer(FloatLayout):
    """The CropObjectRenderer class is responsible for listening to
    the cropobject dict in the model and rendering it upon itself.
    Its place is attached as an overlay of the editor widget (the image)
    with the same size and position.

    In order to force rendering the annotations, add 1 to the
    ``rendnerer.redraw`` property, which fires redrawing.
    """
    # Maybe the ObjectGraphRenderer could be folded into this?
    # To work above the selectable_cropobjects?

    selectable_cropobjects = DictProperty()

    adapter = ObjectProperty()
    view = ObjectProperty()
    editor_widget = ObjectProperty()

    cropobject_keys = ListProperty()
    cropobject_keys_mask = DictProperty(None)

    mlclasses_colors = DictProperty()

    # The following properties are used to correctly resize
    # the intermediate CropObject structures.
    model_image_height = NumericProperty()
    model_image_width = NumericProperty()

    height_ratio_in = NumericProperty(1)
    old_height_ratio_in = NumericProperty(1)
    width_ratio_in = NumericProperty(1)
    old_width_ratio_in = NumericProperty(1)

    redraw = NumericProperty(0)
    '''Signals that the CropObjects need to be redrawn.'''

    def __init__(self, annot_model, editor_widget, **kwargs):
        super(CropObjectRenderer, self).__init__(**kwargs)

        # Bindings for model changes.
        # These bindings are what causes changes in the model to propagate
        # to the view. However, the DictProperty in the model does not
        # signal changes to the dicts it contains, only insert/delete states.
        # This implies that e.g. moving a CropObject does not trigger the
        # self.update_cropobject_data() binding.
        annot_model.bind(cropobjects=self.update_cropobject_data)

        # This is just a misc operation, to keep the renderer
        # in a valid state when the user loads a different MLClassList.
        annot_model.bind(mlclasses=self.recompute_mlclasses_color_dict)

        # Bindings for view changes
        editor_widget.bind(height=self.editor_height_changed)
        editor_widget.bind(width=self.editor_width_changed)

        self.size = editor_widget.size
        self.pos = editor_widget.pos

        # The self.selectable_cropobjects level of indirection only
        # handles numpy to kivy world conversion. This can be handled
        # in the adapter conversion method, maybe?
        self.adapter = DictAdapter(
            data=self.selectable_cropobjects,
            args_converter=self.selectable_cropobject_converter,
            selection_mode='multiple',
            cls=CropObjectView,
        )

        self.view = CropObjectListView(adapter=self.adapter,
                                       size_hint=(None, None),
                                       size=self.size, #(self.size[0] / 2, self.size[1] / 2),
                                       pos=self.pos)
        self.adapter.bind(on_selection_change=self.view.broadcast_selection)
        self.adapter.bind(on_selection_change=self.view.sync_selection_with_adapter)

        # Keyboard event trapping implemented there.
        Window.bind(on_key_down=self.view.on_key_down)
        Window.bind(on_key_up=self.view.on_key_up)

        self.model_image_height = annot_model.image.shape[0]
        self.height_ratio_in = old_div(float(editor_widget.height), annot_model.image.shape[0])
        self.model_image_width = annot_model.image.shape[1]
        self.width_ratio_in = old_div(float(editor_widget.width), annot_model.image.shape[1])

        annot_model.bind(image=self.update_image_size)

        # self.view = ListView(item_strings=map(str, range(100)))
        self.add_widget(self.view)
        # The Renderer gets added to the editor externally, though, during
        # app build. That enables us to add or remove the renderer from
        # the active widget tree.

        self.redraw += 1
        logging.info('Render: Initialized CropObjectRenderer, with size {0}'
                     ' and position {1}, ratios {2}. Total keys: {3}'
                     ''.format(self.size, self.pos,
                               (self.height_ratio_in, self.width_ratio_in),
                               len(self.cropobject_keys)))

    def on_redraw(self, instance, pos):
        """This signals that the CropObjects need to be re-drawn. For example,
        adding a CropObject necessitates this, or resizing the window."""
        self.view.adapter.cached_views = dict()
        if self.cropobject_keys_mask is None:
            self.view.adapter.data = self.selectable_cropobjects
        else:
            self.view.adapter.data = {objid: c for objid, c in self.selectable_cropobjects.items()
                                      if self.cropobject_keys_mask[objid]}
            logging.info('Render: After masking: {0} of {1} cropobjects remaining.'
                         ''.format(len(self.view.adapter.data), len(self.selectable_cropobjects)))

        # self.view.slow_populate()
        self.view.populate()
        logging.info('Render: Redrawn {0} times'.format(self.redraw))

    def update_image_size(self, instance, pos):
        prev_editor_height = self.height_ratio_in * self.model_image_height
        self.model_image_height = pos.shape[0]
        self.height_ratio_in = old_div(prev_editor_height, self.model_image_height)

        prev_editor_width = self.width_ratio_in * self.model_image_width
        self.model_image_width = pos.shape[1]
        self.width_ratio_in = old_div(prev_editor_width, self.model_image_width)

    def on_height_ratio_in(self, instance, pos):
        _n_items_changed = 0
        if self.height_ratio_in == 0:
            return
        for objid, c in self.selectable_cropobjects.items():
            orig_c = copy.deepcopy(c)
            c.height *= old_div(self.height_ratio_in, self.old_height_ratio_in)
            c.x *= old_div(self.height_ratio_in, self.old_height_ratio_in)
            self.selectable_cropobjects[objid] = c
            if _n_items_changed < 0:
                logging.info('Render: resizing\n{0}\nto\n{1}'
                             ''.format(' | '.join(str(orig_c).replace('\t', '').split('\n')[1:-1]),
                                       ' | '.join(str(c).replace('\t', '').split('\n')[1:-1])))
            _n_items_changed += 1
        logging.info('Render: Redraw from on_height_ratio_in: ratio {0}, changed {1} items'
                     ''.format(old_div(self.height_ratio_in, self.old_height_ratio_in),
                               _n_items_changed))
        self.old_height_ratio_in = self.height_ratio_in
        self.redraw += 1

    def on_width_ratio_in(self, instance, pos):
        _n_items_changed = 0
        if self.width_ratio_in == 0:
            return
        for objid, c in self.selectable_cropobjects.items():
            orig_c = copy.deepcopy(c)
            c.width *= old_div(self.width_ratio_in, self.old_width_ratio_in)
            c.y *= old_div(self.width_ratio_in, self.old_width_ratio_in)
            self.selectable_cropobjects[objid] = c
            if _n_items_changed < 0:
                logging.info('Render: resizing\n{0}\nto\n{1}'
                             ''.format(' | '.join(str(orig_c).replace('\t', '').split('\n')[1:-1]),
                                       ' | '.join(str(c).replace('\t', '').split('\n')[1:-1])))
            _n_items_changed += 1
        logging.info('Render: Redraw from on_width_ratio_in: ratio {0}, changed {1} items'
                     ''.format(old_div(self.width_ratio_in, self.old_width_ratio_in),
                               _n_items_changed))
        self.old_width_ratio_in = self.width_ratio_in
        self.redraw += 1

    def editor_height_changed(self, instance, pos):
        logging.info('Render: Editor height changed to {0}'.format(pos))
        self.height_ratio_in = old_div(float(pos), self.model_image_height)

    def editor_width_changed(self, instance, pos):
        logging.info('Render: Editor width changed to {0}'.format(pos))
        self.width_ratio_in = old_div(float(pos), self.model_image_width)

    def update_cropobject_data(self, instance, pos):
        """Fired on change in the current CropObject list: make sure
        the data structures underlying the CropObjectViews are in sync
        with the model.

        This is where the positioning magic happens. Once we fit
        the original CropObject to the widget, we're done.

        However, in the future, we need to re-do the positioning magic
        on CropObjectList import. Let's do it here now for testing
        the concepts...
        """
        # Placeholder operation: just copy this for now.
        logging.info('Render: Updating CropObject data, {0} cropobjects'
                     ' and {1} currently selectable.'
                     ''.format(len(pos), len(self.selectable_cropobjects)))

        # Clear current cropobjects. Since ``pos`` is the entire
        # CropObject dictionary from the model and the CropObjects
        # will all be re-drawn anyway, we want selectable_cropobjects
        # to match it exactly.
        self.selectable_cropobjects = {}

        for objid in pos:

            corrected_position_cropobject = copy.deepcopy(pos[objid])
            # X is vertical, Y is horizontal.
            # X is the upper left corner relative to the image. We need the
            # bottom left corner to be X. We first need to get the top-down
            # coordinate for the bottom corner (x + height), then flip it
            # around relative to the current editor height
            # (self.model_image_height - ...) then scale it down
            # (* self.height_ratio_in).
            corrected_position_cropobject.x = (self.model_image_height -
                                               (pos[objid].x + pos[objid].height)) *\
                                              self.height_ratio_in
            corrected_position_cropobject.y = pos[objid].y * self.width_ratio_in
            corrected_position_cropobject.height = corrected_position_cropobject.height *\
                                                   self.height_ratio_in
            corrected_position_cropobject.width = corrected_position_cropobject.width *\
                                                  self.width_ratio_in

            self.selectable_cropobjects[objid] = corrected_position_cropobject
            # Inversion!
            # self.selectable_cropobjects[objid].y = self.height - pos[objid].y
            self.cropobject_keys_mask[objid] = True

        self.cropobject_keys = list(map(str, list(self.selectable_cropobjects.keys())))

        # The adapter data doesn't change automagically
        # when the DictProperty it was bound to changes.
        # Force redraw.
        logging.info('Render: Redrawing from update_cropobject_data')
        self.redraw += 1

    def model_coords_to_editor_coords(self, x, y, height, width):
        """Converts coordinates of a model CropObject into the corresponding
        CropObjectView coordinates."""
        x_out = (self.model_image_height - (x + height)) * self.height_ratio_in
        y_out = y * self.width_ratio_in
        height_out = height * self.height_ratio_in
        width_out = width * self.width_ratio_in
        return x_out, y_out, height_out, width_out

    def recompute_mlclasses_color_dict(self, instance, pos):
        """On MLClassList change, the color dictionary needs to be updated."""
        logging.info('Render: Recomputing mlclasses color dict...')
        for clsid in pos:
            clsname = pos[clsid].name
            self.mlclasses_colors[clsname] = pos[clsid].color

    def selectable_cropobject_converter(self, row_index, rec):
        """Interfacing the CropObjectView and the intermediate data structure.
        Note that as it currently stands, this intermediate structure is
        also a CropObject, although the position params X and Y have been
        switched around."""
        if max(self.mlclasses_colors[rec.clsname]) > 1.0:
            rgb = tuple([old_div(float(x), 255.0) for x in self.mlclasses_colors[rec.clsname]])
        else:
            rgb = tuple([float(x) for x in self.mlclasses_colors[rec.clsname]])
        output = {
            #'text': str(rec.objid),
            #'size_hint': (None, None),
            'is_selected': False,
            'selectable_cropobject': rec,
            'rgb': rgb,
        }
        # logging.debug('Render: Converter fired, input object {0}/{1}, with output:\n{2}'
        #               ''.format(row_index, rec, output))
        return output

    def clear(self, instance, pos):
        logging.info('Render: clear() called with instance {0}, pos {1}'
                     ''.format(instance, pos))
        self.selectable_cropobjects = {}
        self.cropobject_keys = []
        self.cropobject_keys_mask = {}

        self.redraw += 1

    def mask_all(self):
        logging.info('Render: mask() called')
        self.view.unselect_all()  # ...but they disappear anyway?
        self.cropobject_keys_mask = {objid: False
                                     for objid in self.selectable_cropobjects}
        self.redraw += 1

    def unmask_all(self):
        logging.info('Render: mask() called')
        self.cropobject_keys_mask = {objid: True
                                     for objid in self.selectable_cropobjects}
        self.redraw += 1

    def on_adapter(self, instance, pos):
        # logging.info('Render: Selectable cropobjects changed, populating view.')
        logging.info('Render: Something changed in the adapter!')
