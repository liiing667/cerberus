# -*- coding: utf-8 -*-

from cerberus import schema_registry, rules_set_registry, Validator, errors
from cerberus.tests import (
    assert_fail,
    assert_normalized,
    assert_schema_error,
    assert_success,
)


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


class RefConstraintValidator(Validator):
    MULTIPLE_OF = errors.ErrorDefinition(0x100, 'multiple_of')

    def _validate_multiple_of(self, constraint, field, value):
        """{'type': 'dict'}"""
        if not isinstance(value, int) or value % 2:
            self._error(field, self.MULTIPLE_OF)


def test_error_constraint_resolves_nested_references():
    rules_set_registry.extend(
        (
            ('constraint_ref_base', {'multiple_of': 3}),
            ('constraint_ref_wrapper', {'inner': {'$ref': 'constraint_ref_base'}}),
            ('constraint_ref_top', {'$ref': 'constraint_ref_wrapper'}),
        )
    )

    schema = {'foo': {'multiple_of': {'$ref': 'constraint_ref_top'}}}
    validator = RefConstraintValidator(schema)

    assert not validator({'foo': 5})

    error = validator._errors[0]
    assert error.constraint == {'inner': {'multiple_of': 3}}
    assert error.unresolved_refs == ()


def test_error_constraint_keeps_missing_reference():
    schema = {'foo': {'multiple_of': {'$ref': 'constraint_ref_missing'}}}
    validator = RefConstraintValidator(schema)

    assert not validator({'foo': 5})

    error = validator._errors[0]
    assert error.constraint == {'$ref': 'constraint_ref_missing'}
    assert error.unresolved_refs == ('constraint_ref_missing',)


def test_error_constraint_reference_cycle():
    rules_set_registry.extend(
        (
            ('constraint_ref_cycle_a', {'$ref': 'constraint_ref_cycle_b'}),
            ('constraint_ref_cycle_b', {'$ref': 'constraint_ref_cycle_a'}),
        )
    )

    schema = {'foo': {'multiple_of': {'$ref': 'constraint_ref_cycle_a'}}}
    validator = RefConstraintValidator(schema)

    assert not validator({'foo': 5})

    error = validator._errors[0]
    assert error.constraint == {'$ref': 'constraint_ref_cycle_a'}
    assert error.unresolved_refs == ('constraint_ref_cycle_a',)
