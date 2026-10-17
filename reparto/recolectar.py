"""Recolección de los aportes de un día y su atribución a cada dev. Sin LLM."""
from datetime import datetime, time, timedelta


def ventana(dia, cfg):
    """[inicio, fin) del día `dia`: de un corte al siguiente, en hora local."""
    h, m = map(int, cfg.corte.split(":"))
    ini = datetime.combine(dia, time(h, m), cfg.zona)
    return ini, ini + timedelta(days=1)


def dia_cerrado(ahora, cfg):
    """Último día cuya ventana ya terminó en el instante `ahora`."""
    h, m = map(int, cfg.corte.split(":"))
    return (ahora.astimezone(cfg.zona) - timedelta(hours=h, minutes=m)).date() - timedelta(days=1)
