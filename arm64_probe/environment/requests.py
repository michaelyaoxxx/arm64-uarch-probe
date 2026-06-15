from arm64_probe.domain.models import EnvironmentRequirement
from arm64_probe.environment.constants import CONTROLLER_ORDER
from arm64_probe.environment.models import ControllerRequest


def requests_from_requirements(
    requirements: tuple[EnvironmentRequirement, ...],
) -> tuple[ControllerRequest, ...]:
    order = {controller_id: index for index, controller_id in enumerate(CONTROLLER_ORDER)}
    requests: list[ControllerRequest] = []
    seen: set[str] = set()
    for requirement in requirements:
        if requirement.scope != "host":
            raise ValueError(f"requirement {requirement.id} is not host-scoped")
        if not requirement.mutation:
            raise ValueError(f"requirement {requirement.id} is not a mutation")
        controller_id = requirement.capability_id
        if controller_id not in order:
            raise ValueError(f"unsupported environment controller: {controller_id}")
        if controller_id in seen:
            raise ValueError(f"duplicate environment controller: {controller_id}")
        seen.add(controller_id)
        requests.append(ControllerRequest(controller_id, requirement.values))
    return tuple(sorted(requests, key=lambda request: order[request.controller_id]))
