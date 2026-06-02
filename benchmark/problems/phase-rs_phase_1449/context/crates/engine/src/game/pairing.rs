use crate::types::card_type::CoreType;
use crate::types::game_state::GameState;
use crate::types::identifiers::ObjectId;
use crate::types::zones::Zone;
use crate::{
    game::filter::{matches_target_filter, FilterContext},
    types::{
        ability::{TargetFilter, TargetRef},
        player::PlayerId,
    },
};

/// CR 702.95b-d: A soulbond pair is symmetric and both creatures can have only
/// one partner.
pub fn pair_objects(state: &mut GameState, first: ObjectId, second: ObjectId) {
    if first == second {
        return;
    }
    break_pair(state, first);
    break_pair(state, second);
    if let Some(obj) = state.objects.get_mut(&first) {
        obj.paired_with = Some(second);
    }
    if let Some(obj) = state.objects.get_mut(&second) {
        obj.paired_with = Some(first);
    }
    state.layers_dirty = true;
}

pub fn break_pair(state: &mut GameState, object_id: ObjectId) {
    let partner = state
        .objects
        .get_mut(&object_id)
        .and_then(|obj| obj.paired_with.take());
    if let Some(partner_id) = partner {
        if let Some(partner_obj) = state.objects.get_mut(&partner_id) {
            if partner_obj.paired_with == Some(object_id) {
                partner_obj.paired_with = None;
            }
        }
        state.layers_dirty = true;
    }
}

pub fn is_unpaired_creature_you_control(
    state: &GameState,
    object_id: ObjectId,
    controller: PlayerId,
) -> bool {
    state.objects.get(&object_id).is_some_and(|obj| {
        obj.zone == Zone::Battlefield
            && obj.controller == controller
            && obj.paired_with.is_none()
            && obj.card_types.core_types.contains(&CoreType::Creature)
    })
}

pub fn legal_pair_choices(
    state: &GameState,
    source_id: ObjectId,
    controller: PlayerId,
    filter: &TargetFilter,
) -> Vec<ObjectId> {
    if !is_unpaired_creature_you_control(state, source_id, controller) {
        return Vec::new();
    }

    let ctx = FilterContext::from_source_with_controller(source_id, controller);
    state
        .battlefield
        .iter()
        .copied()
        .filter(|&object_id| {
            matches_target_filter(state, object_id, filter, &ctx)
                && is_unpaired_creature_you_control(state, object_id, controller)
        })
        .collect()
}

pub fn legal_pair_choice_refs(
    state: &GameState,
    source_id: ObjectId,
    controller: PlayerId,
    filter: &TargetFilter,
) -> Vec<TargetRef> {
    legal_pair_choices(state, source_id, controller, filter)
        .into_iter()
        .map(TargetRef::Object)
        .collect()
}

/// CR 702.95e: A pair ends if either object leaves the battlefield, stops
/// being a creature, or stops being under the same controller.
pub fn cleanup_invalid_pairs(state: &mut GameState) {
    let to_break: Vec<ObjectId> = state
        .objects
        .iter()
        .filter_map(|(&id, obj)| {
            let partner_id = obj.paired_with?;
            let Some(partner) = state.objects.get(&partner_id) else {
                return Some(id);
            };
            let valid = obj.zone == Zone::Battlefield
                && partner.zone == Zone::Battlefield
                && obj.controller == partner.controller
                && obj.card_types.core_types.contains(&CoreType::Creature)
                && partner.card_types.core_types.contains(&CoreType::Creature)
                && partner.paired_with == Some(id);
            (!valid).then_some(id)
        })
        .collect();

    for id in to_break {
        break_pair(state, id);
    }
}
