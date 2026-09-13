from app.contracts.models import TrialResult,content_hash
from app.lab.reproduction import reproduced

def trial(i,*,failed=True,world=None,triggered=True,lifecycle='COMPLETED'):
    return TrialResult(episode_id=f'e{i}',world_id=world or f'w{i}',scenario_hash=content_hash('s'),policy_hash=content_hash('p'),arm='B0',trial_index=i,lifecycle=lifecycle,outcome='VIOLATION' if failed else 'COMPLETED',failed_checks=['C3'] if failed else [],fault_scheduled=True,fault_triggered=triggered)

def test_three_fresh_trials_not_cached_transcripts():
    assert reproduced([trial(i) for i in range(3)],'C3')
    assert not reproduced([trial(i,world='same') for i in range(3)],'C3')
    assert not reproduced([trial(0),trial(1),trial(2,failed=False)],'C3')
    assert not reproduced([trial(0),trial(1),trial(2,triggered=False)],'C3')
    assert not reproduced([trial(0),trial(1),trial(2,lifecycle='INTERRUPTED')],'C3')
