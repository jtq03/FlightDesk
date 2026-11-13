"""Hardware boundary. Preview is deliberately not presented as physical rotation."""
from typing import Protocol


class DisplayDriver(Protocol):
    async def request_rotation(self, angle: int) -> dict: ...
    async def status(self) -> dict: ...


class PreviewDisplay:
    async def request_rotation(self, angle):
        return {'mode': 'preview', 'requested_angle': angle, 'applied_angle': None,
                'touch_verified': False, 'message': 'Layout preview only; Pi display driver awaits hardware validation.'}

    async def status(self):
        return {'mode': 'preview', 'applied_angle': None, 'touch_verified': False}

def save_desktop_transform(path, output, angle):
    """Keep the existing desktop profile consistent with the app's saved choice."""
    import os, re
    if not path.exists():
        return False
    text = path.read_text()
    if not text.strip():
        text = 'profile {\n    output ' + output + ' enable transform normal\n}\n'
    transform = 'normal' if angle == 0 else str(angle)
    pattern = r'(?m)^([ \t]*output[ \t]+' + re.escape(output) + r')(?=[ \t]|$)([^\n]*)$'
    def change(match):
        options, sep, comment = match[2].partition('#')
        if re.search(r'\btransform[ \t]+\S+', options):
            options = re.sub(r'\btransform[ \t]+\S+', 'transform ' + transform, options)
        else:
            options = options.rstrip() + ' transform ' + transform + ' '
        return match[1] + options + (sep + comment if sep else '')
    updated, count = re.subn(pattern, change, text)
    if not count:
        return False
    if updated != path.read_text():
        temporary = path.with_name(path.name + '.flightdesk.tmp')
        temporary.write_text(updated)
        temporary.chmod(path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    return True


class WaylandDisplay:
    """Apply only configured, validated orientations to the Pi's DSI output."""
    def __init__(self, output, socket='wayland-0'):
        import re
        if not re.fullmatch(r'DSI-[0-9]+', output) or not re.fullmatch(r'wayland-[0-9]+', socket):
            raise ValueError('Invalid display configuration')
        self.output, self.socket, self.angle = output, socket, None
        self.profile_saved = False

    async def request_rotation(self, angle):
        import asyncio, os
        if angle not in (0, 90, 180, 270):
            raise ValueError('Invalid rotation')
        env = os.environ.copy()
        env.update(WAYLAND_DISPLAY=self.socket, XDG_RUNTIME_DIR='/run/user/%d' % os.getuid())
        proc = await asyncio.create_subprocess_exec('wlr-randr', '--output', self.output, '--transform',
                  'normal' if angle == 0 else str(angle), env=env,
                  stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            _, err = await asyncio.wait_for(proc.communicate(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill(); await proc.wait()
            raise ValueError('Display did not respond; orientation unchanged')
        if proc.returncode:
            raise ValueError('Display rotation failed: ' + err.decode(errors='replace')[:200])
        self.angle = angle
        from pathlib import Path
        profile = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config'))) / 'kanshi/config'
        try:
            self.profile_saved = save_desktop_transform(profile, self.output, angle)
            if self.profile_saved:
                # kanshi rereads its existing profile on SIGHUP; scope to this user.
                reload = await asyncio.create_subprocess_exec('pkill', '-HUP', '-u', str(os.getuid()), '-x', 'kanshi',
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(reload.wait(), timeout=3)
        except (OSError, asyncio.TimeoutError):
            self.profile_saved = False
        return await self.status()

    async def status(self):
        return {'mode': 'wayland', 'applied_angle': self.angle, 'touch_verified': False,
                'desktop_profile_saved': self.profile_saved, 'message': 'Orientation applied; saved choices persist across restarts.'}
