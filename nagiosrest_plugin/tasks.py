from contextlib import contextmanager
import os
import subprocess
import tempfile
import requests

from cloudify import ctx as cloudify_ctx
from cloudify.decorators import operation
from cloudify.exceptions import RecoverableError, NonRecoverableError


def _get_desired_value(key,
                       args,
                       instance_attr,
                       node_prop):
    return (args.get(key) or
            instance_attr.get(key) or
            node_prop.get(key))


def _get_base_url(ctx, entity_type, address):
    return 'https://{address}/nagiosrest/{entity_type}s/{tenant}'.format(
        address=address,
        entity_type=entity_type,
        tenant=cloudify_ctx.tenant_name,
    )


def _get_instance_id_url(ctx, operation_inputs):
    props = _get_desired_value('nagiosrest_monitoring',
                               operation_inputs,
                               ctx.instance.runtime_properties,
                               ctx.node.properties)
    address = props.get('address',
                        ctx.node.properties['nagiosrest_monitoring']
                        ['address'])
    return (
        '{base_url}'
        '/{deployment}/{instance_id}'
    ).format(
        base_url=_get_base_url(ctx, 'target', address),
        deployment=props['deployment_override'] or ctx.deployment.id,
        instance_id=ctx.instance.id,
    )


def _get_group_url(ctx, operation_inputs):
    props = _get_desired_value('nagiosrest_monitoring',
                               operation_inputs,
                               ctx.instance.runtime_properties,
                               ctx.node.properties)
    address = props.get('address',
                        ctx.node.properties['nagiosrest_monitoring']
                        ['address'])
    return (
        '{base_url}'
        '/{group_type}/{group_name}'
    ).format(
        base_url=_get_base_url(ctx, 'group', address),
        group_type=_get_desired_value('group_type', operation_inputs,
                                      ctx.instance.runtime_properties,
                                      ctx.node.properties),
        group_name=_get_desired_value('group_name', operation_inputs,
                                      ctx.instance.runtime_properties,
                                      ctx.node.properties)
    )


def _get_metagroup_url(ctx, operation_inputs):
    props = _get_desired_value('nagiosrest_monitoring',
                               operation_inputs,
                               ctx.instance.runtime_properties,
                               ctx.node.properties)
    address = props.get('address',
                        ctx.node.properties['nagiosrest_monitoring']
                        ['address'])

    return (
        '{base_url}'
        '/{group_type}/{group_instance_prefix}'
    ).format(
        base_url=_get_base_url(ctx, 'metagroup', address),
        group_type=ctx.node.properties['group_type'],
        group_instance_prefix=ctx.node.properties['group_instance_prefix'],
    )


def _get_instance_ip(ctx, operation_inputs):
    props = _get_desired_value('nagiosrest_monitoring',
                               operation_inputs,
                               ctx.instance.runtime_properties,
                               ctx.node.properties)
    ip = props.get('instance_ip_property',
                   ctx.node.properties['nagiosrest_monitoring']
                   ['instance_ip_property'])

    try:
        return ctx.instance.runtime_properties[ip]
    except KeyError:
        return ctx.node.properties[ip]


def _get_credentials(ctx, operation_inputs):
    props = _get_desired_value('nagiosrest_monitoring',
                               operation_inputs,
                               ctx.instance.runtime_properties,
                               ctx.node.properties)
    return props['username'], props['password']


@contextmanager
def _get_cert(ctx, operation_inputs):
    props = _get_desired_value('nagiosrest_monitoring',
                               operation_inputs,
                               ctx.instance.runtime_properties,
                               ctx.node.properties)
    cert = props['certificate']
    tmpdir = tempfile.mkdtemp(prefix='nagiosrestcert_')
    cert_path = os.path.join(tmpdir, 'cert')
    with open(cert_path, 'w') as cert_handle:
        cert_handle.write(cert)
    try:
        yield cert_path
    finally:
        subprocess.check_call(['rm', '-rf', tmpdir])


def _make_call(ctx, request_method, url, data, operation_inputs):
    with _get_cert(ctx, operation_inputs) as cert:
        result = request_method(
            url,
            auth=_get_credentials(ctx, operation_inputs),
            json=data,
            verify=cert,
        )

    if result.status_code >= 500:
        raise RecoverableError(
            'Server is currently unavailable. '
            'Call was to {url}, and '
            'response was {code}: {details}'.format(
                url=url,
                code=result.status_code,
                details=result.text,
            )
        )
    elif result.status_code >= 400:
        raise NonRecoverableError(
            'Parameters passed to server were incorrect. '
            'Call was to {url}, and '
            'response was {code}: {details}'.format(
                url=url,
                code=result.status_code,
                details=result.text,
            )
        )
    else:
        return result


@operation
def add_monitoring(ctx, **operation_inputs):
    props = _get_desired_value('nagiosrest_monitoring',
                               operation_inputs,
                               ctx.instance.runtime_properties,
                               ctx.node.properties)
    url = _get_instance_id_url(ctx, operation_inputs)
    _make_call(
        ctx,
        requests.put,
        url,
        {
            'instance_ip': _get_instance_ip(ctx, operation_inputs),
            'target_type': props['target_type'],
            'groups': props['groups'],
        },
        operation_inputs,
    )


@operation
def remove_monitoring(ctx, **operation_inputs):
    url = _get_instance_id_url(ctx, operation_inputs)
    _make_call(
        ctx,
        requests.delete,
        url,
        None,
        operation_inputs,
    )


@operation
def create_group(ctx, **operation_inputs):
    reaction_target = _get_desired_value('reaction_target', operation_inputs,
                                         ctx.instance.runtime_properties,
                                         ctx.node.properties)
    url = _get_group_url(ctx, operation_inputs)
    _make_call(
        ctx,
        requests.put,
        url,
        {
            'reaction_target': reaction_target,
        },
        operation_inputs,
    )


@operation
def delete_group(ctx, **operation_inputs):
    url = _get_group_url(ctx, operation_inputs)
    _make_call(
        ctx,
        requests.delete,
        url,
        None,
        operation_inputs,
    )


@operation
def create_meta_group(ctx, **operation_inputs):
    url = _get_metagroup_url(ctx, operation_inputs)

    data = {
        'approach': _get_desired_value('approach', operation_inputs,
                                       ctx.instance.runtime_properties,
                                       ctx.node.properties),

        'unknown': _get_desired_value('unknown', operation_inputs,
                                      ctx.instance.runtime_properties,
                                      ctx.node.properties),
        'target': _get_desired_value('target', operation_inputs,
                                     ctx.instance.runtime_properties,
                                     ctx.node.properties)
    }
    for prop in (
        'interval',
        'low_warning_threshold',
        'low_critical_threshold',
        'high_warning_threshold',
        'high_critical_threshold',
        'low_reaction',
        'high_reaction',
    ):
        prop_val = _get_desired_value(prop, operation_inputs,
                                      ctx.instance.runtime_properties,
                                      ctx.node.properties)
        if prop_val:
            data[prop] = prop_val

    _make_call(
        ctx,
        requests.put,
        url,
        data,
        operation_inputs,
    )


@operation
def delete_meta_group(ctx, **operation_inputs):
    url = _get_metagroup_url(ctx, operation_inputs)
    _make_call(
        ctx,
        requests.delete,
        url,
        None,
        operation_inputs,
    )
