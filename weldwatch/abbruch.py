"""Abbruch eines laufenden Scans (kooperativ: vor jedem Texterkennungsaufruf und zwischen den Zeichnungen)."""
import threading


class Abgebrochen(BaseException):
    """BaseException, damit allgemeine 'except Exception'-Blöcke den Abbruch nicht verschlucken."""


_ereignis = threading.Event()


def anfordern():
    _ereignis.set()


def zuruecksetzen():
    _ereignis.clear()


def gesetzt():
    return _ereignis.is_set()


def pruefen():
    if _ereignis.is_set():
        raise Abgebrochen()
