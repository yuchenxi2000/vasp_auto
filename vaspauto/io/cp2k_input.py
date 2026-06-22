"""
parse cp2k input files (v2.0)
author: YCX
"""
import dataclasses


indent_str = '    '


def str2bool(s: str) -> bool:
    return s.lower().startswith(('t', '.t', 'y'))


@dataclasses.dataclass
class KeyValue:
    k = ''
    v = ''

    @classmethod
    def from_kv(cls, k, v):
        obj = cls()
        obj.k = k
        obj.v = v
        return obj

    def iter_lines(self, indent: int = 0):
        yield indent_str * indent + self.k + ' ' + self.v


@dataclasses.dataclass
class Section:
    name = ''
    params = ''
    subsecs: 'list[Section]' = dataclasses.field(default_factory=list)
    kvs: 'list[KeyValue]' = dataclasses.field(default_factory=list)

    @classmethod
    def empty_sec_with_name(cls, name):
        obj = cls()
        obj.name = name
        return obj

    def subsec_from_path(self, path_name_list: list, create_if_not_exist: bool = True):
        subsec = self
        for name in path_name_list:
            subsubsec = None
            for sec in subsec.subsecs:
                if sec.name == name:
                    subsubsec = sec
            if subsubsec is None:
                if create_if_not_exist:
                    # create if not exist
                    new_sec = Section.empty_sec_with_name(name)
                    subsec.subsecs.append(new_sec)
                    subsec = new_sec
                else:
                    return None
            else:
                subsec = subsubsec
        return subsec

    def insert(self, path: str, other, create_if_not_exist: bool = True) -> bool:
        names = path.split('/')
        subsec = self.subsec_from_path(names[:-1], create_if_not_exist=create_if_not_exist)
        if subsec is not None:
            if isinstance(other, Section):
                subsec.subsecs.append(other)
            else:
                if isinstance(other, KeyValue):
                    subsec.kvs.append(KeyValue.from_kv(names[-1], other.v))
                else:
                    subsec.kvs.append(KeyValue.from_kv(names[-1], str(other)))
            return True
        else:
            return False

    def set(self, path: str, other, create_if_not_exist: bool = True) -> bool:
        names = path.split('/')
        subsec = self.subsec_from_path(names[:-1], create_if_not_exist=create_if_not_exist)
        if subsec is not None:
            if isinstance(other, Section):
                subsec.del_subsec(other.name)
                subsec.subsecs.append(other)
            else:
                subsec.del_kv(names[-1])
                if isinstance(other, KeyValue):
                    subsec.kvs.append(KeyValue.from_kv(names[-1], other.v))
                elif isinstance(other, list):
                    for value in other:
                        subsec.kvs.append(KeyValue.from_kv(names[-1], str(value)))
                else:
                    subsec.kvs.append(KeyValue.from_kv(names[-1], str(other)))
            return True
        else:
            return False

    def set_param(self, path: str, other, create_if_not_exist: bool = True) -> bool:
        names = path.split('/')
        subsec = self.subsec_from_path(names, create_if_not_exist=create_if_not_exist)
        if subsec is not None:
            subsec.params = str(other)
            return True
        else:
            return False

    def get_kv(self, path: str):
        names = path.split('/')
        subsec = self.subsec_from_path(names[:-1], create_if_not_exist=False)
        if subsec is None:
            return None
        else:
            for kv in subsec.kvs:
                if kv.k == names[-1]:
                    return kv.v
            return None

    def get_subsec(self, path: str):
        names = path.split('/')
        subsec = self.subsec_from_path(names[:-1], create_if_not_exist=False)
        if subsec is None:
            return None
        else:
            for sec in subsec.subsecs:
                if sec.name == names[-1]:
                    return sec
            return None

    def get_param(self, path: str):
        names = path.split('/')
        subsec = self.subsec_from_path(names, create_if_not_exist=False)
        if subsec is None:
            return None
        else:
            return subsec.params

    def del_kv(self, path):
        names = path.split('/')
        subsec = self.subsec_from_path(names[:-1], create_if_not_exist=False)
        if subsec is not None:
            for i in range(len(subsec.kvs) - 1, -1, -1):
                if subsec.kvs[i].k == names[-1]:
                    del subsec.kvs[i]

    def del_subsec(self, path):
        names = path.split('/')
        subsec = self.subsec_from_path(names[:-1], create_if_not_exist=False)
        if subsec is not None:
            for i in range(len(subsec.subsecs) - 1, -1, -1):
                if subsec.subsecs[i].name == names[-1]:
                    del subsec.subsecs[i]

    def del_param(self, path):
        names = path.split('/')
        subsec = self.subsec_from_path(names, create_if_not_exist=False)
        if subsec is not None:
            subsec.params = ''

    def update(self, other):
        self.params = other.params
        for kv in other.kvs:
            self.del_kv(kv.k)
        for kv in other.kvs:
            self.insert(kv.k, kv.v)
        for subsec in other.subsecs:
            subsec_in_self = self.get_subsec(subsec.name)
            if subsec_in_self is not None:
                subsec_in_self.update(subsec)
            else:
                self.insert(subsec.name, subsec)

    def parse(self, lines, line_idx):
        while line_idx < len(lines):
            line = lines[line_idx]
            line = line.strip()
            if line.startswith(('!', '#')) or line == '':
                line_idx += 1
                continue
            line = line.split('!', maxsplit=1)[0]
            line = line.split('#', maxsplit=1)[0]
            if line.startswith('&'):
                data = line[1:].split(maxsplit=1)
                if data[0].upper() == 'END':
                    return line_idx + 1
                else:
                    current_sec = Section()
                    current_sec.name = data[0]
                    current_sec.params = data[1] if len(data) > 1 else ''
                    line_idx = current_sec.parse(lines, line_idx + 1)
                    self.subsecs.append(current_sec)
            else:
                data = line.split(maxsplit=1)
                kv = KeyValue()
                kv.k = data[0]
                kv.v = data[1] if len(data) >= 2 else ''
                self.kvs.append(kv)
                line_idx += 1
        return line_idx

    def iter_lines(self, indent: int = 0, global_obj: bool = False):
        if not global_obj:
            yield indent_str * indent + '&' + self.name + ' ' + self.params
        for kv in self.kvs:
            for line in kv.iter_lines(indent + 1 if not global_obj else indent):
                yield line
        for sub in self.subsecs:
            for line in sub.iter_lines(indent + 1 if not global_obj else indent):
                yield line
        if not global_obj:
            yield indent_str * indent + '&END'

    def to_str(self, global_obj: bool = True):
        s = ''
        for line in self.iter_lines(global_obj=global_obj):
            s += line + '\n'
        return s

    @classmethod
    def from_file(cls, filepath):
        obj = cls()
        lines = []
        with open(filepath, 'r') as fin:
            for line in fin:
                lines.append(line)
        obj.parse(lines, 0)
        return obj

    @classmethod
    def from_str(cls, s: str, name: str = ''):
        obj = cls.empty_sec_with_name(name)
        lines = s.split('\n')
        obj.parse(lines, 0)
        return obj

    @classmethod
    def from_lines(cls, lines, name: str = ''):
        obj = cls.empty_sec_with_name(name)
        obj.parse(lines, 0)
        return obj

    @classmethod
    def from_dict(cls, d: dict, name: str = ''):
        obj = cls.empty_sec_with_name(name)
        for dk in d:
            if isinstance(d[dk], dict):
                subsec = cls.from_dict(d[dk])
                subsec.name = dk
                obj.subsecs.append(subsec)
            elif dk == '_':
                obj.params = str(d[dk])
            else:
                kv = KeyValue()
                kv.k = dk
                kv.v = str(d[dk])
                obj.kvs.append(kv)
        return obj

    def to_dict(self):
        d = {}
        if self.params != '':
            d['_'] = self.params
        for kv in self.kvs:
            d[kv.k] = kv.v
        for subsec in self.subsecs:
            d[subsec.name] = subsec.to_dict()
        return d

    def write_file(self, filepath):
        with open(filepath, 'w') as fout:
            for line in self.iter_lines(global_obj=True):
                fout.write(line + '\n')

    def __str__(self):
        return self.to_str()
