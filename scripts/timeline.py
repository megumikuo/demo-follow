"""Reversible source/output time mapping for global and regional playback speed."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Span:
    start: float
    end: float
    speed: float
    output_start: float

    @property
    def output_end(self):
        return self.output_start + (self.end - self.start) / self.speed


class Timeline:
    def __init__(self, duration, speed=1., segments=None):
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError('Duration must be finite and positive')
        self._speed(speed)
        ordered = sorted(segments or [], key=lambda s: s['start'])
        regions, previous = [], 0.
        for s in ordered:
            start, end, rate = float(s['start']), float(s['end']), float(s['speed'])
            self._speed(rate)
            if not all(math.isfinite(v) for v in (start, end)) or not previous <= start < end <= duration:
                raise ValueError('Speed segments must be within the recording and must not overlap')
            if start > previous:
                regions.append((previous, start, speed))
            regions.append((start, end, rate))
            previous = end
        if previous < duration:
            regions.append((previous, duration, speed))
        self.spans, output = [], 0.
        for start, end, rate in regions:
            span = Span(start, end, rate, output)
            self.spans.append(span)
            output = span.output_end
        self.duration, self.source_duration = output, duration

    @staticmethod
    def _speed(rate):
        if not math.isfinite(rate) or not .25 <= rate <= 3.:
            raise ValueError('Speed must be finite and between 0.25 and 3')

    def source_at(self, t):
        t = min(self.duration, max(0., t))
        for s in self.spans:
            if t <= s.output_end:
                return min(s.end, s.start + (t-s.output_start)*s.speed)
        return self.source_duration

    def output_at(self, t):
        t = min(self.source_duration, max(0., t))
        for s in self.spans:
            if t <= s.end:
                return s.output_start + (t-s.start)/s.speed
        return self.duration

    def serializable(self):
        return [dict(source_start=s.start, source_end=s.end, speed=s.speed,
                     output_start=s.output_start, output_end=s.output_end) for s in self.spans]
