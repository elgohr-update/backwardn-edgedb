##
# Copyright (c) 2008-2010 Sprymix Inc.
# All rights reserved.
#
# See LICENSE for details.
##


import copy
import io

import importlib
import collections
import itertools

from semantix.utils import graph, lang
from semantix.utils.lang import yaml
from semantix.utils.nlang import morphology

from semantix import caos
from semantix.caos import proto
from semantix.caos import backends


class MetaError(caos.MetaError):
    def __init__(self, error, context=None):
        super().__init__(error)
        self.context = context

    def __str__(self):
        result = super().__str__()
        if self.context:
            result += '\ncontext: %s, line %d, column %d' % \
                        (self.context.name, self.context.start.line, self.context.start.column)
        return result


class LangObject(yaml.Object):
    @classmethod
    def get_canonical_class(cls):
        for base in cls.__bases__:
            if issubclass(base, caos.types.ProtoObject):
                return base

        return cls


class WordCombination(LangObject, wraps=morphology.WordCombination):
    def construct(self):
        if isinstance(self.data, str):
            morphology.WordCombination.__init__(self, self.data)
        else:
            word = morphology.WordCombination.from_dict(self.data)
            self.forms = word.forms
            self.value = self.forms.get('singular', next(iter(self.forms.values())))

    def represent(self, dumper):
        return dumper.represent_mapping('tag:yaml.org,2002:map', self.as_dict())


class AtomModExpr(LangObject, wraps=proto.AtomModExpr):
    def construct(self):
        proto.AtomModExpr.__init__(self, self.data['expr'], context=self.context)

    def represent(self, dumper):
        result = {'expr': next(iter(self.exprs[0]))}
        return dumper.represent_mapping('tag:yaml.org,2002:map', result)


class AtomModMinLength(LangObject, wraps=proto.AtomModMinLength):
    def construct(self):
        proto.AtomModMinLength.__init__(self, self.data['min-length'], context=self.context)

    def represent(self, dumper):
        result = {'min-length': self.value}
        return dumper.represent_mapping('tag:yaml.org,2002:map', result)


class AtomModMaxLength(LangObject, wraps=proto.AtomModMaxLength):
    def construct(self):
        proto.AtomModMaxLength.__init__(self, self.data['max-length'], context=self.context)

    def represent(self, dumper):
        result = {'max-length': self.value}
        return dumper.represent_mapping('tag:yaml.org,2002:map', result)


class AtomModRegExp(LangObject, wraps=proto.AtomModRegExp):
    def construct(self):
        proto.AtomModRegExp.__init__(self, self.data['regexp'], context=self.context)

    def represent(self, dumper):
        result = {'regexp': next(iter(self.regexps[0]))}
        return dumper.represent_mapping('tag:yaml.org,2002:map', result)


class Atom(LangObject, wraps=proto.Atom):
    def construct(self):
        data = self.data
        proto.Atom.__init__(self, name=None, backend=data.get('backend'), base=data['extends'],
                           default=data['default'], title=data['title'],
                           description=data['description'], is_abstract=data['abstract'])
        mods = data.get('mods')
        if mods:
            for mod in mods:
                self.add_mod(mod)

    def represent(self, dumper):
        result = {
            'extends': str(self.base)
        }

        if self.base:
            result['extends'] = self.base

        if self.default is not None:
            result['default'] = self.default

        if self.title:
            result['title'] = self.title

        if self.description:
            result['description'] = self.description

        if self.is_abstract:
            result['abstract'] = self.is_abstract

        if self.mods:
            result['mods'] = list(itertools.chain.from_iterable(self.mods.values()))

        return dumper.represent_mapping('tag:yaml.org,2002:map', result)


class Concept(LangObject, wraps=proto.Concept):
    def construct(self):
        data = self.data
        extends = data.get('extends')
        if extends:
            if not isinstance(extends, list):
                extends = [extends]

        proto.Concept.__init__(self, name=None, backend=data.get('backend'), base=extends,
                              title=data.get('title'), description=data.get('description'),
                              is_abstract=data.get('abstract'))
        self._links = data.get('links', {})

    def represent(self, dumper):
        result = {
            'extends': [str(i) for i in itertools.chain(self.base, self.custombases)]
        }

        if self.title:
            result['title'] = self.title

        if self.description:
            result['description'] = self.description

        if self.is_abstract:
            result['abstract'] = self.is_abstract

        if self.ownlinks:
            result['links'] = {str(k): v for k, v in self.ownlinks.items()}

        return dumper.represent_mapping('tag:yaml.org,2002:map', result)


class LinkProperty(LangObject, wraps=proto.LinkProperty):
    def construct(self):
        data = self.data
        if isinstance(data, str):
            proto.LinkProperty.__init__(self, name=None, atom=data)
        else:
            atom_name, info = next(iter(data.items()))
            proto.LinkProperty.__init__(self, name=None, atom=atom_name, title=info['title'],
                                       description=info['description'])
            self.mods = info.get('mods')


class LinkDef(LangObject, wraps=proto.Link):
    def construct(self):
        data = self.data
        extends = data.get('extends')
        if extends:
            if not isinstance(extends, list):
                extends = [extends]

        proto.Link.__init__(self, name=None, backend=data.get('backend'), base=extends,
                            title=data['title'], description=data['description'],
                            is_abstract=data.get('abstract'))
        for property_name, property in data['properties'].items():
            property.name = property_name
            self.add_property(property)

    def represent(self, dumper):
        result = {}

        if not self.implicit_derivative:
            if self.base:
                result['extends'] = [str(i) for i in self.base]

        if self.title:
            result['title'] = self.title

        if self.description:
            result['description'] = self.description

        if self.is_abstract:
            result['abstract'] = self.is_abstract

        if self.mapping:
            result['mapping'] = self.mapping

        if isinstance(self.target, proto.Atom) and self.target.automatic:
            result['mods'] = list(itertools.chain.from_iterable(self.target.mods.values()))

        if self.source:
            result['required'] = self.required

        return dumper.represent_mapping('tag:yaml.org,2002:map', result)


class LinkSet(LangObject, wraps=proto.LinkSet):
    def represent(self, dumper):
        result = {}

        for l in self.links:
            if isinstance(l.target, proto.Atom) and l.target.automatic:
                key = l.target.base
            else:
                key = l.target.name
            result[str(key)] = l

        return dumper.represent_mapping('tag:yaml.org,2002:map', result)


class LinkList(LangObject, list):

    def construct(self):
        data = self.data
        if isinstance(data, str):
            link = proto.Link(source=None, target=data, name=None)
            link.context = self.context
            self.append(link)
        elif isinstance(data, list):
            for target in data:
                link = proto.Link(source=None, target=target, name=None)
                link.context = self.context
                self.append(link)
        else:
            for target, info in data.items():
                link = proto.Link(name=None, target=target, mapping=info['mapping'],
                                 required=info['required'], title=info['title'],
                                 description=info['description'])
                link.mods = info.get('mods')
                link.context = self.context
                self.append(link)


class MetaSet(LangObject):
    def construct(self):
        data = self.data
        context = self.context

        if context.document.import_context.builtin:
            self.include_builtin = True
            realm_meta_class = proto.BuiltinRealmMeta
        else:
            self.include_builtin = False
            realm_meta_class = proto.RealmMeta

        self.finalindex = realm_meta_class()

        self.toplevel = context.document.import_context.toplevel
        globalindex = context.document.import_context.metaindex

        localindex = realm_meta_class()
        self.module = data.get('module', None)
        if not self.module:
            self.module = context.document.module.__name__
        localindex.add_module(self.module, None)

        for alias, module in context.document.imports.items():
            localindex.add_module(module.__name__, alias)

        self.read_atoms(data, globalindex, localindex)
        self.read_links(data, globalindex, localindex)
        self.read_concepts(data, globalindex, localindex)

        if self.toplevel:
            # The final pass on concepts may produce additional links and atoms,
            # thus, it has to be performed first.
            concepts = self.order_concepts(globalindex)
            links = self.order_links(globalindex)
            atoms = self.order_atoms(globalindex)

            for atom in atoms:
                if self.include_builtin or atom.name.module != 'semantix.caos.builtins':
                    self.finalindex.add(atom)

            for link in links:
                if self.include_builtin or link.name.module != 'semantix.caos.builtins':
                    self.finalindex.add(link)

            for concept in concepts:
                if self.include_builtin or concept.name.module != 'semantix.caos.builtins':
                    self.finalindex.add(concept)


    def read_atoms(self, data, globalmeta, localmeta):
        backend = data.get('backend')

        for atom_name, atom in data['atoms'].items():
            atom.name = caos.Name(name=atom_name, module=self.module)
            atom.backend = backend
            globalmeta.add(atom)
            localmeta.add(atom)

        for atom in localmeta('atom', include_builtin=self.include_builtin):
            if atom.base:
                try:
                    atom.base = localmeta.normalize_name(atom.base, include_pyobjects=True)
                except caos.MetaError as e:
                    raise MetaError(e, atom.context) from e


    def order_atoms(self, globalmeta):
        g = {}

        for atom in globalmeta('atom', include_automatic=True, include_builtin=self.include_builtin):
            g[atom.name] = {"item": atom, "merge": [], "deps": []}

            if atom.base:
                atom_base = globalmeta.get(atom.base, include_pyobjects=True)
                if isinstance(atom_base, proto.Atom):
                    atom.base = atom_base.name
                    if atom.base.module != 'semantix.caos.builtins':
                        g[atom.name]['deps'].append(atom.base)

        return graph.normalize(g, merger=None)


    def read_links(self, data, globalmeta, localmeta):
        for link_name, link in data['links'].items():
            module = self.module
            link.name = caos.Name(name=link_name, module=module)

            properties = {}
            for property_name, property in link.properties.items():
                property.name = caos.Name(name=link_name + '__' + property_name, module=module)
                property.atom = localmeta.normalize_name(property.atom)
                properties[property.name] = property
            link.properties = properties

            globalmeta.add(link)
            localmeta.add(link)

        for link in localmeta('link', include_builtin=self.include_builtin):
            if link.base:
                link.base = [localmeta.normalize_name(b) for b in link.base]
            elif link.name != 'semantix.caos.builtins.link':
                link.base = [caos.Name('semantix.caos.builtins.link')]


    def order_links(self, globalmeta):
        g = {}

        for link in globalmeta('link', include_automatic=True, include_builtin=True):
            for property_name, property in link.properties.items():
                if not isinstance(property.atom, proto.Prototype):
                    property.atom = globalmeta.get(property.atom)

                    mods = getattr(property, 'mods', None)
                    if mods:
                        # Got an inline atom definition.
                        default = getattr(property, 'default', None)
                        atom = self.genatom(link, property.atom.name, default, property_name, mods)
                        globalmeta.add(atom)
                        property.atom = atom

            if link.source and not isinstance(link.source, proto.Prototype):
                link.source = globalmeta.get(link.source)

            if link.target and not isinstance(link.target, proto.Prototype):
                link.target = globalmeta.get(link.target)

            g[link.name] = {"item": link, "merge": [], "deps": []}

            if link.implicit_derivative and not link.atomic():
                base = globalmeta.get(next(iter(link.base)))
                if base.is_atom:
                    raise caos.MetaError('implicitly defined atomic link % used to link to concept' %
                                         link.name)

            if link.base:
                g[link.name]['merge'].extend(link.base)

        return graph.normalize(g, merger=proto.Link.merge)


    def read_concepts(self, data, globalmeta, localmeta):
        backend = data.get('backend')

        for concept_name, concept in data['concepts'].items():
            concept.name = caos.Name(name=concept_name, module=self.module)
            concept.backend = backend

            if globalmeta.get(concept.name, None):
                raise caos.MetaError('%s already defined' % concept.name)

            globalmeta.add(concept)
            localmeta.add(concept)

        for concept in localmeta('concept', include_builtin=self.include_builtin):
            bases = []
            custombases = []

            if concept.base:
                for b in concept.base:
                    base_name = localmeta.normalize_name(b, include_pyobjects=True)
                    if proto.Concept.is_prototype(base_name):
                        bases.append(base_name)
                    else:
                        cls = localmeta.get(base_name, include_pyobjects=True)
                        if not issubclass(cls, caos.concept.Concept):
                            raise caos.MetaError('custom concept base classes must inherit from '
                                                 'caos.concept.Concept: %s' % base_name)
                        custombases.append(base_name)

            if not bases and concept.name != 'semantix.caos.builtins.Object':
                bases.append(caos.Name('semantix.caos.builtins.Object'))

            concept.base = bases
            concept.custombases = custombases

            for link_name, links in concept._links.items():
                for link in links:
                    link.source = concept.name
                    link.target = localmeta.normalize_name(link.target)

                    link_qname = localmeta.normalize_name(link_name, default=None)
                    if not link_qname:
                        # The link has not been defined globally.
                        if not caos.Name.is_qualified(link_name):
                            # If the name is not fully qualified, assume inline link definition.
                            # The only attribute that is used for global definition is the name.
                            link_qname = caos.Name(name=link_name, module=self.module)
                            linkdef = proto.Link(name=link_qname, base=[caos.Name('semantix.caos.builtins.link')])
                            linkdef.is_atom = globalmeta.get(link.target, type=proto.Atom, default=None) is not None
                            globalmeta.add(linkdef)
                            localmeta.add(linkdef)
                        else:
                            link_qname = caos.Name(link_name)

                    # A new implicit subclass of the link is created for each (source, link_name, target)
                    # combination
                    link.base = {link_qname}
                    link.implicit_derivative = True
                    link_genname = proto.Link.gen_link_name(link.source, link.target, link_qname.name)
                    link.name = caos.Name(name=link_genname, module=link_qname.module)
                    globalmeta.add(link)
                    localmeta.add(link)
                    concept.add_link(link)


    def order_concepts(self, globalmeta):
        g = {}

        for concept in globalmeta('concept', include_builtin=True):
            links = {}
            link_target_types = {}

            for link_name, links in concept.links.items():
                for link in links:
                    if not isinstance(link.source, proto.Prototype):
                        link.source = globalmeta.get(link.source)

                    if not isinstance(link.target, proto.Prototype):
                        link.target = globalmeta.get(link.target)
                        if isinstance(link.target, caos.types.ProtoConcept):
                            link.target.add_rlink(link)

                    if isinstance(link.target, proto.Atom):
                        if link_name in link_target_types and link_target_types[link_name] != 'atom':
                            raise caos.MetaError('%s link is already defined as a link to non-atom')

                        mods = getattr(link, 'mods', None)
                        if mods:
                            # Got an inline atom definition.
                            default = getattr(link, 'default', None)
                            atom = self.genatom(concept, link.target.name, default, link_name, mods)
                            globalmeta.add(atom)
                            link.target = atom

                        if link.mapping != '11':
                            raise caos.MetaError('%s: links to atoms can only have a "1 to 1" mapping'
                                                 % link_name)

                        link_target_types[link_name] = 'atom'
                    else:
                        if link_name in link_target_types and link_target_types[link_name] == 'atom':
                            raise caos.MetaError('%s link is already defined as a link to atom')

                        link_target_types[link_name] = 'concept'

            g[concept.name] = {"item": concept, "merge": [], "deps": []}
            if concept.base:
                g[concept.name]["merge"].extend(concept.base)

        return graph.normalize(g, merger=proto.Concept.merge)


    def genatom(self, host, base, default, link_name, mods):
        atom_name = '__' + host.name.name + '__' + link_name.name
        atom = proto.Atom(name=caos.Name(name=atom_name, module=host.name.module),
                         base=base,
                         default=default,
                         automatic=True,
                         backend=host.backend)
        for mod in mods:
            atom.add_mod(mod)
        return atom


    def items(self):
        return itertools.chain([('_index_', self.finalindex)], self.finalindex.index_by_name.items())


class EntityShell(LangObject, wraps=caos.concept.EntityShell):
    def __init__(self, data, context):
        super().__init__(data=data, context=context)
        caos.concept.EntityShell.__init__(self)

    def construct(self):
        if isinstance(self.data, str):
            self.id = self.data
        else:
            aliases = {alias: mod.__name__ for alias, mod in self.context.document.imports.items()}
            factory = self.context.document.realm.getfactory(module_aliases=aliases)

            concept, data = next(iter(self.data.items()))
            self.entity = factory(concept)(**data)
            self.context.document.entities.append(self.entity)


class RealmMeta(LangObject, wraps=proto.RealmMeta):
    def represent(self, dumper):
        result = {'atoms': {}, 'links': {}, 'concepts': {}}

        for type in ('atom', 'link', 'concept'):
            for obj in self(type=type, include_builtin=False, include_automatic=False):
                # XXX
                if type == 'link' and obj.implicit_derivative:
                    continue
                result[type + 's'][str(obj.name)] = obj

        return dumper.represent_mapping('tag:yaml.org,2002:map', result)


class DataSet(LangObject):
    def construct(self):

        entities = {id: [shell.entity for shell in shells] for id, shells in self.data.items()}
        for entity in self.context.document.entities:
            entity.materialize_links(entities)


class CaosName(LangObject, wraps=caos.Name):
    def represent(self, dumper):
        return dumper.represent_scalar('tag:yaml.org,2002:str', str(self))


class ModuleFromData:
    def __init__(self, name):
        self.__name__ = name


class Backend(backends.MetaBackend):

    def __init__(self, module=None, data=None):
        super().__init__()

        if module:
            self.metadata = module
        else:
            import_context = proto.ImportContext('<string>', toplevel=True)
            module = ModuleFromData('<string>')
            context = lang.meta.DocumentContext(module=module, import_context=import_context)
            for k, v in lang.yaml.Language.load_dict(io.StringIO(data), context):
                setattr(module, str(k), v)
            self.metadata = module


    def getmeta(self):
        return self.metadata._index_

    def dump_meta(self, meta):
        prologue = '%SCHEMA semantix.caos.backends.yaml.schemas.Semantics\n---\n'
        return prologue + yaml.Language.dump(meta)

    def get_delta(self, meta):
        mymeta = self.getmeta()
        delta = mymeta.delta(meta)
        return delta
