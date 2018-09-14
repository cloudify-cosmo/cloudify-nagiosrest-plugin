from contextlib import contextmanager
import os
import subprocess
import tempfile

import requests

from cloudify import ctx as cloudify_ctx
from cloudify.decorators import operation
from cloudify.exceptions import RecoverableError, NonRecoverableError


def _get_base_url(ctx, entity_type):
    return 'https://{address}/nagiosrest/{entity_type}s/{tenant}'.format(
        address=ctx.node.properties['nagiosrest_monitoring']['address'],
        entity_type=entity_type,
        tenant=cloudify_ctx.tenant_name,
    )


def _get_instance_id_url(ctx):
    props = ctx.node.properties['nagiosrest_monitoring']
    return (
        '{base_url}'
        '/{deployment}/{instance_id}'
    ).format(
        base_url=_get_base_url(ctx, 'target'),
        deployment=props['deployment_override'] or ctx.deployment.id,
        instance_id=ctx.instance.id,
    )


def _get_group_url(ctx):
    return (
        '{base_url}'
        '/{group_type}/{group_name}'
    ).format(
        base_url=_get_base_url(ctx, 'group'),
        group_type=ctx.node.properties['group_type'],
        group_name=ctx.node.properties['group_name'],
    )


def _get_metagroup_url(ctx):
    return (
        '{base_url}'
        '/{group_type}/{group_instance_prefix}'
    ).format(
        base_url=_get_base_url(ctx, 'metagroup'),
        group_type=ctx.node.properties['group_type'],
        group_instance_prefix=ctx.node.properties['group_instance_prefix'],
    )


def _get_instance_ip(ctx):
    ip = ctx.node.properties['nagiosrest_monitoring']['instance_ip_property']
    try:
        return ctx.instance.runtime_properties[ip]
    except KeyError:
        return ctx.node.properties[ip]


def _get_credentials(ctx):
    props = ctx.node.properties['nagiosrest_monitoring']
    return props['username'], props['password']


@contextmanager
def _get_cert(ctx):
    props = ctx.node.properties['nagiosrest_monitoring']
    cert = props['certificate']
    tmpdir = tempfile.mkdtemp(prefix='nagiosrestcert_')
    cert_path = os.path.join(tmpdir, 'cert')
    with open(cert_path, 'w') as cert_handle:
        cert_handle.write(cert)
    try:
        yield cert_path
    finally:
        subprocess.check_call(['rm', '-rf', tmpdir])


def _make_call(ctx, request_method, url, data):
    with _get_cert(ctx) as cert:
        result = request_method(
            url,
            auth=_get_credentials(ctx),
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
def add_monitoring(ctx):
    props = ctx.node.properties['nagiosrest_monitoring']
    url = _get_instance_id_url(ctx)
    _make_call(
        ctx,
        requests.put,
        url,
        {
            'instance_ip': _get_instance_ip(ctx),
            'target_type': props['target_type'],
            'groups': props['groups'],
        },
    )


@operation
def remove_monitoring(ctx):
    url = _get_instance_id_url(ctx)
    _make_call(
        ctx,
        requests.delete,
        url,
        None,
    )


@operation
def create_group(ctx):
    props = ctx.node.properties
    url = _get_group_url(ctx)
    _make_call(
        ctx,
        requests.put,
        url,
        {
            'reaction_target': props['reaction_target'],
        },
    )


@operation
def create_meta_group(ctx):
    props = ctx.node.properties
    url = _get_metagroup_url(ctx)

    data = {
        'approach': props['approach'],
        'unknown': props['unknown'],
        'target': props['target'],
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
        if props.get(prop):
            data[prop] = props[prop]

    _make_call(
        ctx,
        requests.put,
        url,
        data,
    )
