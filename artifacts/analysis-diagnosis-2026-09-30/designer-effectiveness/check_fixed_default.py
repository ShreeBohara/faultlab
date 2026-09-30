"""$0 offline check of the proposed fixed-default intervention rule against the five rebuilt diagnosis contexts.

Reads only the JSON files written by investigation A (inv-a/*-diagnosis-context.json). No store, network or provider.
"""
import json, pathlib

HERE = pathlib.Path(__file__).resolve().parent
INV_A = HERE.parent / 'inv-a'

PROTOCOL = 'faultlab-diagnosis-selection/v2-fixed-default'
HYPOTHESIS = ('Fixed default ({protocol}): the Mechanic named no valid intervention, so fixed code selected the first '
              'declared option whose reduction trials already showed {target} in 3 of 3 valid control trials and in 0 of '
              '3 valid treatment trials. Tested claim only: under the incumbent policy, the schedule change {change} '
              'removes the {target} violation in three fresh paired trials. No explanation of the agent\'s failure is '
              'claimed.')


def eligible_control(obs):
    return obs is not None and obs['valid_trials'] == 3 and obs['target_violations'] == 3


def eligible_treatment(obs):
    return obs is not None and obs['fresh_trials'] == 3 and obs['valid_trials'] == 3 and obs['target_violations'] == 0


def default_option(context):
    if not eligible_control(context.get('observed_control_trials')):
        return None
    for option in context['interventions']:  # declared (neighbors) order, first four
        if eligible_treatment(option.get('observed_treatment_trials')):
            return option['id'], option['change']
    return None


# What each run's Mechanic answer did (investigation A, mechanic-outputs.json): selected id or None.
MECHANIC_SELECTED = {
    'v2d-dev5': 'intervention-7b8a13a6ed07a7ba054e44e8',
    'v2e-dev5': None,                      # valid answer, requested null
    'v2f-dev5': 'intervention-eb9f974e4d0e1b0e60ab2070',
    'v2g-dev5': None,                      # both answers invalid (614-char hypothesis)
    'v2g-dev6': 'intervention-1fa1cf42ff627b60cfa631dd',
}

rows = []
for name, mech in MECHANIC_SELECTED.items():
    context = json.loads((INV_A / f'{name}-diagnosis-context.json').read_text())
    default = default_option(context)
    selected = mech or (default[0] if default else None)
    by = 'MECHANIC' if mech else ('FIXED_DEFAULT' if default else 'NONE')
    hyp = HYPOTHESIS.format(protocol=PROTOCOL, target=context['target_invariant'], change=default[1]) if default else None
    rows.append({'run': name, 'target': context['target_invariant'], 'options': len(context['interventions']),
                 'fixed_default': default[0] if default else None, 'mechanic_selected': mech,
                 'selected_by_under_rule': by, 'selected_under_rule': selected,
                 'fixed_hypothesis_chars': len(hyp) if hyp else None})

# Negative shapes: the eac3d243 decline (every option already 1/3), a flaky control, a partly invalid treatment.
def shape(control, treatments):
    return {'observed_control_trials': control,
            'interventions': [{'id': f'intervention-{i}', 'change': f'c{i}', 'observed_treatment_trials': t} for i, t in enumerate(treatments)]}
ok = {'fresh_trials': 3, 'valid_trials': 3, 'target_violations': 3}
negatives = {
    'all_options_one_of_three (eac3d243 shape)': shape(ok, [{'fresh_trials': 3, 'valid_trials': 3, 'target_violations': 1}] * 4),
    'control_two_of_three': shape({'fresh_trials': 3, 'valid_trials': 3, 'target_violations': 2}, [{'fresh_trials': 3, 'valid_trials': 3, 'target_violations': 0}]),
    'treatment_two_valid': shape(ok, [{'fresh_trials': 3, 'valid_trials': 2, 'target_violations': 0}]),
    'treatment_untested': shape(ok, [None]),
}
neg = {k: default_option(v) for k, v in negatives.items()}

longest = HYPOTHESIS.format(protocol=PROTOCOL, target='C8', change='lower_parameter:1:completion_delay_ticks:99')
out = {'rows': rows, 'negatives': neg, 'longest_plausible_hypothesis_chars': len(longest), 'limit': 600}
(HERE / 'fixed_default_check.json').write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
