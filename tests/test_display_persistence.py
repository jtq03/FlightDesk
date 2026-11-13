import asyncio
from pathlib import Path
import pytest
from flightdesk.display import save_desktop_transform, PreviewDisplay
from flightdesk.store import Store
from flightdesk.runtime import Runtime


def test_desktop_profile_changes_only_this_output(tmp_path):
    p=tmp_path/'config';p.write_text('profile {\n output DSI-2 enable mode 720x1280 transform normal\n output HDMI-A-1 enable transform normal\n}\n');p.chmod(0o600)
    assert save_desktop_transform(p,'DSI-2',90)
    assert 'DSI-2 enable mode 720x1280 transform 90' in p.read_text()
    assert 'HDMI-A-1 enable transform normal' in p.read_text()
    assert p.stat().st_mode&0o777==0o600
    assert save_desktop_transform(p,'DSI-2',0)
    assert 'DSI-2 enable mode 720x1280 transform normal' in p.read_text()
    assert not save_desktop_transform(tmp_path/'missing','DSI-2',90)


def test_failed_rotation_keeps_previous_saved_choice(tmp_path):
    class RejectingDisplay(PreviewDisplay):
        async def request_rotation(self,angle):
            if angle==270:raise ValueError('Unavailable')
            return await super().request_rotation(angle)
    async def check():
        store=Store(tmp_path);runtime=Runtime(store,display=RejectingDisplay())
        try:
            await runtime.rotate(90)
            with pytest.raises(ValueError):await runtime.rotate(270)
            assert store.read()['display']['confirmed_angle']==90
            assert store.read()['display']['requested_angle']==90
        finally:await runtime.stop();store.close()
    asyncio.run(check())


def test_empty_desktop_profile_gets_a_persistent_output(tmp_path):
    p=tmp_path/'config';p.write_text('')
    assert save_desktop_transform(p,'DSI-2',90)
    assert 'output DSI-2 enable transform 90' in p.read_text()
