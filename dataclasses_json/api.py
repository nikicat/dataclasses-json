import abc
import functools
import json
from enum import Enum
from typing import (Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar,
                    Union)

from marshmallow.fields import Field as MarshmallowField
from stringcase import (camelcase, pascalcase, snakecase,
                        spinalcase)  # type: ignore

from dataclasses_json.core import (Json, _ExtendedEncoder, _asdict,
                                   _decode_dataclass)
from dataclasses_json.mm import (JsonData, SchemaType, UndefinedParameterError,
                                 build_schema)
from dataclasses_json.undefined import (_CatchAllUndefinedParameters,
                                        _IgnoreUndefinedParameters,
                                        _RaiseUndefinedParameters)
from dataclasses_json.utils import (_handle_undefined_parameters_safe,
                                    _undefined_parameter_action_safe)

A = TypeVar('A', bound="DataClassJsonMixin")
B = TypeVar('B')
C = TypeVar('C')
Fields = List[Tuple[str, Any]]


class LetterCase(Enum):
    CAMEL = camelcase
    KEBAB = spinalcase
    SNAKE = snakecase
    PASCAL = pascalcase


class Undefined(Enum):
    """
    Choose the behavior what happens when an undefined parameter is encountered during class initialization.
    """
    INCLUDE = _CatchAllUndefinedParameters
    RAISE = _RaiseUndefinedParameters
    EXCLUDE = _IgnoreUndefinedParameters


def config(metadata: dict = None, *,
           encoder: Callable = None,
           decoder: Callable = None,
           mm_field: MarshmallowField = None,
           letter_case: Callable[[str], str] = None,
           undefined: Optional[Union[str, Undefined]] = None,
           field_name: str = None) -> Dict[str, dict]:
    if metadata is None:
        metadata = {}

    data = metadata.setdefault('dataclasses_json', {})

    if encoder is not None:
        data['encoder'] = encoder

    if decoder is not None:
        data['decoder'] = decoder

    if mm_field is not None:
        data['mm_field'] = mm_field

    if field_name is not None:
        if letter_case is not None:
            @functools.wraps(letter_case)
            def override(_, _letter_case=letter_case, _field_name=field_name):
                return _letter_case(_field_name)
        else:
            def override(_, _field_name=field_name):
                return _field_name
        letter_case = override

    if letter_case is not None:
        data['letter_case'] = letter_case

    if undefined is not None:
        # Get the corresponding action for undefined parameters
        if isinstance(undefined, str):
            if not hasattr(Undefined, undefined.upper()):
                valid_actions = list(action.name for action in Undefined)
                raise UndefinedParameterError(
                    f"Invalid undefined parameter action, "
                    f"must be one of {valid_actions}")
            undefined = Undefined[undefined.upper()]

        data['undefined'] = undefined

    return metadata


class DataClassJsonMixin(abc.ABC):
    """
    DataClassJsonMixin is an ABC that functions as a Mixin.

    As with other ABCs, it should not be instantiated directly.
    """
    dataclass_json_config = None

    def to_json(self,
                *,
                skipkeys: bool = False,
                ensure_ascii: bool = True,
                check_circular: bool = True,
                allow_nan: bool = True,
                indent: Optional[Union[int, str]] = None,
                separators: Tuple[str, str] = None,
                default: Callable = None,
                sort_keys: bool = False,
                **kw) -> str:
        return json.dumps(self.to_dict(encode_json=False),
                          cls=_ExtendedEncoder,
                          skipkeys=skipkeys,
                          ensure_ascii=ensure_ascii,
                          check_circular=check_circular,
                          allow_nan=allow_nan,
                          indent=indent,
                          separators=separators,
                          default=default,
                          sort_keys=sort_keys,
                          **kw)

    @classmethod
    def from_json(cls: Type[A],
                  s: JsonData,
                  *,
                  encoding=None,
                  parse_float=None,
                  parse_int=None,
                  parse_constant=None,
                  infer_missing=False,
                  **kw) -> A:
        kvs = json.loads(s,
                         encoding=encoding,
                         parse_float=parse_float,
                         parse_int=parse_int,
                         parse_constant=parse_constant,
                         **kw)
        return cls.from_dict(kvs, infer_missing=infer_missing)

    @classmethod
    def from_dict(cls: Type[A],
                  kvs: Json,
                  *,
                  infer_missing=False) -> A:
        return _decode_dataclass(cls, kvs, infer_missing)

    def to_dict(self, encode_json=False) -> Dict[str, Json]:
        return _asdict(self, encode_json=encode_json)

    @classmethod
    def schema(cls: Type[A],
               *,
               infer_missing: bool = False,
               only=None,
               exclude=(),
               many: bool = False,
               context=None,
               load_only=(),
               dump_only=(),
               partial: bool = False,
               unknown=None) -> SchemaType:
        Schema = build_schema(cls, DataClassJsonMixin, infer_missing, partial)

        if unknown is None:
            undefined_parameter_action = _undefined_parameter_action_safe(cls)
            if undefined_parameter_action is not None:
                # We can just make use of the same-named mm keywords
                unknown = undefined_parameter_action.name.lower()

        return Schema(only=only,
                      exclude=exclude,
                      many=many,
                      context=context,
                      load_only=load_only,
                      dump_only=dump_only,
                      partial=partial,
                      unknown=unknown)


def dataclass_json(_cls=None, *, letter_case=None,
                   undefined: Optional[Union[str, Undefined]] = None):
    """
    Based on the code in the `dataclasses` module to handle optional-parens
    decorators. See example below:

    @dataclass_json
    @dataclass_json(letter_case=Lettercase.CAMEL)
    class Example:
        ...
    """

    def wrap(cls):
        return _process_class(cls, letter_case, undefined)

    if _cls is None:
        return wrap
    return wrap(_cls)


def _process_class(cls, letter_case, undefined):
    if letter_case is not None or undefined is not None:
        cls.dataclass_json_config = config(letter_case=letter_case,
                                           undefined=undefined)[
            'dataclasses_json']

    cls.to_json = DataClassJsonMixin.to_json
    # unwrap and rewrap classmethod to tag it to cls rather than the literal
    # DataClassJsonMixin ABC
    cls.from_json = classmethod(DataClassJsonMixin.from_json.__func__)
    cls.to_dict = DataClassJsonMixin.to_dict
    cls.from_dict = classmethod(DataClassJsonMixin.from_dict.__func__)
    cls.schema = classmethod(DataClassJsonMixin.schema.__func__)

    cls.__init__ = _handle_undefined_parameters_safe(cls, kvs=(), usage="init")
    # register cls as a virtual subclass of DataClassJsonMixin
    DataClassJsonMixin.register(cls)
    return cls
