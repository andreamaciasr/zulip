from typing import Sequence

from django.http import HttpRequest, HttpResponse
from django.utils.translation import gettext as _

from zerver.actions.user_groups import (
    bulk_add_members_to_user_group,
    check_add_user_group,
    check_delete_user_group,
    do_update_user_group_description,
    do_update_user_group_name,
    remove_members_from_user_group,
)
from zerver.decorator import require_member_or_admin, require_user_group_edit_permission
from zerver.lib.exceptions import JsonableError
from zerver.lib.request import REQ, has_request_variables
from zerver.lib.response import json_success
from zerver.lib.user_groups import (
    access_user_group_by_id,
    get_direct_memberships_of_users,
    get_user_group_direct_members,
    user_groups_in_realm_serialized,
)
from zerver.lib.users import user_ids_to_users
from zerver.lib.validator import check_int, check_list
from zerver.models import UserProfile
from zerver.views.streams import compose_views


@require_user_group_edit_permission
@has_request_variables
def add_user_group(
    request: HttpRequest,
    user_profile: UserProfile,
    name: str = REQ(),
    members: Sequence[int] = REQ(json_validator=check_list(check_int), default=[]),
    description: str = REQ(),
) -> HttpResponse:
    user_profiles = user_ids_to_users(members, user_profile.realm)
    check_add_user_group(user_profile.realm, name, user_profiles, description)
    return json_success(request)


@require_member_or_admin
@has_request_variables
def get_user_group(request: HttpRequest, user_profile: UserProfile) -> HttpResponse:
    user_groups = user_groups_in_realm_serialized(user_profile.realm)
    return json_success(request, data={"user_groups": user_groups})


@require_user_group_edit_permission
@has_request_variables
def edit_user_group(
    request: HttpRequest,
    user_profile: UserProfile,
    user_group_id: int = REQ(json_validator=check_int, path_only=True),
    name: str = REQ(default=""),
    description: str = REQ(default=""),
) -> HttpResponse:
    if not (name or description):
        raise JsonableError(_("No new data supplied"))

    user_group = access_user_group_by_id(user_group_id, user_profile)

    if name != user_group.name:
        do_update_user_group_name(user_group, name)

    if description != user_group.description:
        do_update_user_group_description(user_group, description)

    return json_success(request)


@require_user_group_edit_permission
@has_request_variables
def delete_user_group(
    request: HttpRequest,
    user_profile: UserProfile,
    user_group_id: int = REQ(json_validator=check_int, path_only=True),
) -> HttpResponse:

    check_delete_user_group(user_group_id, user_profile)
    return json_success(request)


@require_user_group_edit_permission
@has_request_variables
def update_user_group_backend(
    request: HttpRequest,
    user_profile: UserProfile,
    user_group_id: int = REQ(json_validator=check_int, path_only=True),
    delete: Sequence[int] = REQ(json_validator=check_list(check_int), default=[]),
    add: Sequence[int] = REQ(json_validator=check_list(check_int), default=[]),
) -> HttpResponse:
    if not add and not delete:
        raise JsonableError(_('Nothing to do. Specify at least one of "add" or "delete".'))

    thunks = [
        lambda: add_members_to_group_backend(
            request, user_profile, user_group_id=user_group_id, members=add
        ),
        lambda: remove_members_from_group_backend(
            request, user_profile, user_group_id=user_group_id, members=delete
        ),
    ]
    data = compose_views(thunks)

    return json_success(request, data)


def add_members_to_group_backend(
    request: HttpRequest, user_profile: UserProfile, user_group_id: int, members: Sequence[int]
) -> HttpResponse:
    if not members:
        return json_success(request)

    user_group = access_user_group_by_id(user_group_id, user_profile)
    user_profiles = user_ids_to_users(members, user_profile.realm)
    existing_member_ids = set(get_direct_memberships_of_users(user_group, user_profiles))

    for user_profile in user_profiles:
        if user_profile.id in existing_member_ids:
            raise JsonableError(
                _("User {user_id} is already a member of this group").format(
                    user_id=user_profile.id,
                )
            )

    user_profile_ids = [user.id for user in user_profiles]
    bulk_add_members_to_user_group(user_group, user_profile_ids)
    return json_success(request)


def remove_members_from_group_backend(
    request: HttpRequest, user_profile: UserProfile, user_group_id: int, members: Sequence[int]
) -> HttpResponse:
    if not members:
        return json_success(request)

    user_profiles = user_ids_to_users(members, user_profile.realm)
    user_group = access_user_group_by_id(user_group_id, user_profile)
    group_member_ids = get_user_group_direct_members(user_group)
    for member in members:
        if member not in group_member_ids:
            raise JsonableError(_("There is no member '{}' in this user group").format(member))

    user_profile_ids = [user.id for user in user_profiles]
    remove_members_from_user_group(user_group, user_profile_ids)
    return json_success(request)
