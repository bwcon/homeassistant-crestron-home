from homeassistant.helpers import area_registry, entity_registry


async def assign_entity_area(hass, entity_id, room_name):
    """Assign an entity to a Home Assistant area."""
    if not room_name or not entity_id:
        return

    area_reg = area_registry.async_get(hass)
    entity_reg = entity_registry.async_get(hass)

    area = area_reg.async_get_area_by_name(room_name)

    if area is None:
        area = area_reg.async_create(room_name)

    entity_reg.async_update_entity(
        entity_id,
        area_id=area.id,
    )