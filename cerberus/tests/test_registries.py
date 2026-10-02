# -*- coding: utf-8 -*-

from cerberus import errors, schema_registry, rules_set_registry, Validator
from cerberus.tests import (
    assert_fail,
    assert_normalized,
    assert_schema_error,
    assert_success,
)


REF_GUARD_FAILED = errors.ErrorDefinition(0x0F, 'ref_guard')


class RefGuardErrorHandler(errors.BasicErrorHandler):
    messages = errors.BasicErrorHandler.messages.copy()
    messages[REF_GUARD_FAILED.code] = 'ref guard failed'


class RefConstraintValidator(Validator):
    def _validate_ref_guard(self, constraint, field, value):
        """{'type': 'dict'}"""
        self._error(field, REF_GUARD_FAILED)


def test_schema_registry_simple():
    schema_registry.add('foo', {'bar': {'type': 'string'}})
    schema = {'a': {'schema': 'foo'}, 'b': {'schema': 'foo'}}
    document = {'a': {'bar': 'a'}, 'b': {'bar': 'b'}}
    assert_success(document, schema)


def test_top_level_reference():
    schema_registry.add('peng', {'foo': {'type': 'integer'}})
    document = {'foo': 42}
    assert_success(document, 'peng')


def test_rules_set_simple():
    rules_set_registry.add('foo', {'type': 'integer'})
    assert_success({'bar': 1}, {'bar': 'foo'})
    assert_fail({'bar': 'one'}, {'bar': 'foo'})


def test_allow_unknown_as_reference():
    rules_set_registry.add('foo', {'type': 'number'})
    v = Validator(allow_unknown='foo')
    assert_success({0: 1}, {}, v)
    assert_fail({0: 'one'}, {}, v)


def test_recursion():
    rules_set_registry.add('self', {'type': 'dict', 'allow_unknown': 'self'})
    v = Validator(allow_unknown='self')
    assert_success({0: {1: {2: {}}}}, {}, v)


def test_references_remain_unresolved(validator):
    rules_set_registry.extend(
        (('boolean', {'type': 'boolean'}), ('booleans', {'valuesrules': 'boolean'}))
    )
    validator.schema = {'foo': 'booleans'}
    assert 'booleans' == validator.schema['foo']
    assert 'boolean' == rules_set_registry._storage['booleans']['valuesrules']


def test_rules_registry_with_anyof_type():
    rules_set_registry.add('string_or_integer', {'anyof_type': ['string', 'integer']})
    schema = {'soi': 'string_or_integer'}
    assert_success({'soi': 'hello'}, schema)


def test_schema_registry_with_anyof_type():
    schema_registry.add('soi_id', {'id': {'anyof_type': ['string', 'integer']}})
    schema = {'soi': {'schema': 'soi_id'}}
    assert_success({'soi': {'id': 'hello'}}, schema)


def test_normalization_with_rules_set():
    # https://github.com/pyeve/cerberus/issues/283
    rules_set_registry.add('foo', {'default': 42})
    assert_normalized({}, {'bar': 42}, {'bar': 'foo'})
    rules_set_registry.add('foo', {'default_setter': lambda _: 42})
    assert_normalized({}, {'bar': 42}, {'bar': 'foo'})
    rules_set_registry.add('foo', {'type': 'integer', 'nullable': True})
    assert_success({'bar': None}, {'bar': 'foo'})


def test_rules_set_with_dict_field():
    document = {'a_dict': {'foo': 1}}
    schema = {'a_dict': {'type': 'dict', 'schema': {'foo': 'rule'}}}

    # the schema's not yet added to the valid ones, so test the faulty first
    rules_set_registry.add('rule', {'tüpe': 'integer'})
    assert_schema_error(document, schema)

    rules_set_registry.add('rule', {'type': 'integer'})
    assert_success(document, schema)


def test_error_constraint_resolves_nested_registry_references():
    rules_set_registry.add(
        'ref_leaf', {'type': 'integer', 'allowed': [1, 2, 3]}
    )
    rules_set_registry.add(
        'ref_inner', {'$ref': 'ref_leaf'}
    )
    rules_set_registry.add(
        'ref_outer',
        {'type': 'dict', 'valuesrules': {'$ref': 'ref_inner'}},
    )

    document = {'a_field': {'x': 'one'}}
    schema = {'a_field': {'ref_guard': {'$ref': 'ref_outer'}}}
    error = assert_fail(document, schema, RefConstraintValidator())

    assert error[0].constraint == {
        'type': 'dict',
        'valuesrules': {'type': 'integer', 'allowed': [1, 2, 3]},
    }
    assert error[0].constraint_resolved is True
    # the original reference is preserved on the error
    assert error[0]._constraint == {'$ref': 'ref_outer'}
    # the other error fields stay untouched
    assert error[0].rule == 'ref_guard'
    assert error[0].code == REF_GUARD_FAILED.code
    assert error[0].document_path == ('a_field',)
    assert error[0].value == {'x': 'one'}
    # errors() output structure keeps the custom error message
    validator = RefConstraintValidator(schema, error_handler=RefGuardErrorHandler)
    assert not validator(document)
    assert validator.errors == {'a_field': ['ref guard failed']}


def test_error_constraint_keeps_missing_reference():
    schema = {'a_field': {'ref_guard': {'$ref': 'missing_definition'}}}
    validator = RefConstraintValidator(schema)
    error = assert_fail({'a_field': 'x'}, validator=validator)

    assert error[0].constraint == {'$ref': 'missing_definition'}
    assert error[0].constraint_resolved is False


def test_error_constraint_handles_reference_cycles():
    rules_set_registry.add('ref_cycle_a', {'$ref': 'ref_cycle_b'})
    rules_set_registry.add('ref_cycle_b', {'$ref': 'ref_cycle_a'})

    schema = {'a_field': {'ref_guard': {'$ref': 'ref_cycle_a'}}}
    validator = RefConstraintValidator(schema)
    error = assert_fail({'a_field': 'x'}, validator=validator)

    assert error[0].constraint == {'$ref': 'ref_cycle_a'}
    assert error[0].constraint_resolved is False


def test_error_constraint_without_reference_is_unchanged():
    error = assert_fail(
        {'a_field': 'one'},
        {'a_field': {'type': 'integer'}},
    )
    assert error[0].constraint == 'integer'
    assert error[0].constraint_resolved is True
