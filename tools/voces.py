"""Descarga voces para StreamOps.

    python tools/voces.py lista                 muestra el catálogo
    python tools/voces.py instalar miku teto    instala las voces indicadas
    python tools/voces.py instalar todas        instala todo el catálogo
    python tools/voces.py url nombre https://…/modelo.zip [--base es_MX-ald-medium] [--pitch 0]
                                                agrega un modelo RVC de cualquier URL

Las voces Piper funcionan solas. Las voces de personaje son modelos RVC hechos por
fans: necesitan tools\\instalar_rvc.bat y usan una voz Piper como base.
AVISO: un .pth es un archivo pickle; al cargarlo puede ejecutar código. Instala
solo modelos de fuentes en las que confíes.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

VOICES = Path(__file__).resolve().parent.parent / "data" / "voices"
RVC = VOICES / "rvc"
HF = "https://huggingface.co"
PIPER = HF + "/rhasspy/piper-voices/resolve/main/es/{loc}/{name}/{q}/{loc}-{name}-{q}.onnx"
BASE_F = "es_MX-claude-high"  # base femenina
BASE_M = "es_MX-ald-medium"  # base masculina

VALORANT = "astra breach brimstone chamber clove cypher deadlock fade gekko harbor iso jett kayo killjoy neon omen phoenix raze reyna sage skye sova tejo viper vyse yoru".split()

# nombre -> ("piper", url_onnx)  |  ("rvc", [urls], base, tono en semitonos)
CATALOG: dict[str, tuple] = {
    "es_MX-claude-high": ("piper", PIPER.format(loc="es_MX", name="claude", q="high")),
    "es_MX-ald-medium": ("piper", PIPER.format(loc="es_MX", name="ald", q="medium")),
    "es_AR-daniela-high": ("piper", PIPER.format(loc="es_AR", name="daniela", q="high")),
    "es_ES-davefx-medium": ("piper", PIPER.format(loc="es_ES", name="davefx", q="medium")),
    "es_MX-laura-high": ("piper", HF + "/HirCoir/Piper-TTS-Laura/resolve/main/es_MX-laura-high.onnx"),
    "es_ES-glados-medium": ("piper", HF + "/csukuangfj/vits-piper-es_ES-glados-medium/resolve/main/es_ES-glados-medium.onnx"),
    # Voces Piper de personajes hechas por fans. Las «en-» hablan inglés: leen el español con acento.
    "raton-jacky": ("piper", "https://github.com/ikarius6/jacky-voz-tts/raw/main/jacky.onnx"),
    "en-torreta-portal": ("piper", "https://github.com/hyessn/turret-tts-model/raw/main/turret.onnx"),
    "en-anunciador-portal": ("piper", "https://github.com/Davis8483/portal2-announcer-piper-tts/raw/main/announcer.onnx"),
    "en-combine": ("piper", "https://github.com/robit-man/combine_overwatch_onnx/raw/main/overwatch.onnx"),
    "en-hal9000": ("piper", "https://github.com/dividebysandwich/piper-voice-models/raw/main/HAL9000-denoised/en_US-hal_6409-medium.onnx"),
    "en-k9": ("piper", "https://github.com/hopkira/k9_piper_voice/raw/main/k9_model.onnx"),
    "en-bmo": ("piper", "https://github.com/1liminal1/xiaozhi-esphome/raw/main/piper-voices/en_US-bmo_voice.onnx"),
    "en-bt7274": ("piper", "https://github.com/DJMalachite/PiperVoiceModels/raw/main/Titanfall2/BT7274/BT7274.onnx"),
    "en-scorch": ("piper", "https://github.com/DJMalachite/PiperVoiceModels/raw/main/Titanfall2/ScorchAI/ScorchAI.onnx"),
    "en-pda-subnautica": ("piper", "https://github.com/DJMalachite/PiperVoiceModels/raw/main/Subnautica/PDA/PDA.onnx"),
    "en-shodan": ("piper", "https://github.com/TacitusCornelius/shodan-piper-tts/raw/main/shodan_remake/en_US-shodan_remake-medium.onnx"),
    "en-xerxes": ("piper", "https://github.com/TacitusCornelius/shodan-piper-tts/raw/main/Xerxes_medium/en_US-xerxes-medium.onnx"),
    "en-colossus": ("piper", "https://github.com/TacitusCornelius/colossus-tts-voice/raw/main/voices/colossus-medium/en_US-colossus-medium.onnx"),
    "en-cabal": ("piper", "https://github.com/jappeace-sloth/cabal-voice/raw/master/en_US-cabal-medium.onnx"),
    "en-zani": ("piper", "https://github.com/MohitEvil/Zani_Voice_model/raw/main/zani.onnx"),
    "en-glados": ("piper", HF + "/AIHeaven/piper_unofficial_voices/resolve/main/en_US/en_us-glados-high/en_us-glados-high.onnx"),
    "en-wheatley": ("piper", HF + "/davet2001/wheatley1/resolve/main/wheatley1.onnx"),
    "en-cave-johnson": ("piper", HF + "/davet2001/cave_johnson1/resolve/main/cave_johnson1.onnx"),
    "en-jarvis": ("piper", HF + "/jgkawell/jarvis/resolve/main/en/en_GB/jarvis/high/jarvis-high.onnx"),
    "en-optimus": ("piper", HF + "/crazygiscool/optimus-piper-voice/resolve/main/optimus-final.onnx"),
    "en-chitti": ("piper", HF + "/swqg-messiah/kusaal_chitti_piper/resolve/main/chitti.onnx"),
    "en-ahsoka": ("piper", HF + "/crazygiscool/ahsoka-piper-voice/resolve/main/ahsoka-final.onnx"),
    "en-la-muerte": ("piper", HF + "/drewThomasson/piper_tts_finetune_death_from_puss_and_boots/resolve/main/en_US-death-high_onnx/en_US-death-high.onnx"),
    "en-kronk": ("piper", HF + "/russdill/kronk/resolve/main/en/en_US/kronk/medium/kronk-medium.onnx"),
    "en-rocket": ("piper", HF + "/AkumaVenom/RocketRacoon-Piper-US-Medium/resolve/main/rocket_racoon.onnx"),
    "en-cheetah": ("piper", HF + "/HAV0X1014/KF-PiperTTS-voices/resolve/main/Cheetah/en_US-cheetah-high.onnx"),
    "en-silverfox": ("piper", HF + "/HAV0X1014/KF-PiperTTS-voices/resolve/main/silverfox/en_US-silverfox-medium.onnx"),
    "en-megumin": ("piper", HF + "/semioniy/piper-en_US-megumin-medium/resolve/main/model.onnx"),
    "en-tomoko": ("piper", HF + "/quarterturn/kuroki_tomoko_en_piper/resolve/main/kuroki_tomoko.onnx"),
    "en-scaramouche": ("piper", HF + "/jstlntch/Scaramouche_or_Wanderer_voice_model_for_piper/resolve/main/model.onnx"),
    **{f"en-val-{a}": ("piper", HF + f"/fox3000foxy/piper-checkpoints-{a}/resolve/main/{a}.onnx") for a in VALORANT},
    "miku": ("rvc", [HF + "/Alejo520/ModelsByAlejo520/resolve/main/hatsune-miku-Latin-Spanish.zip"], BASE_F, 4),
    "miku-jp": ("rvc", [HF + "/binant/Hatsune_Miku__RVC_v2_/resolve/main/model.pth",
                        HF + "/binant/Hatsune_Miku__RVC_v2_/resolve/main/model.index"], BASE_F, 6),
    "teto": ("rvc", [HF + "/SinsuSquid/Kasane-Teto-UTAU-RVC-v2/resolve/main/KasaneTeto.pth",
                     HF + "/SinsuSquid/Kasane-Teto-UTAU-RVC-v2/resolve/main/KasaneTeto.index"], BASE_F, 2),
    "bob-esponja": ("rvc", [HF + "/EthanRhys/Bob-Esponja-LA/resolve/main/Bob-Esponja-LA.zip"], BASE_M, 6),
    "homero": ("rvc", [HF + "/EthanRhys/Homero-Simpson-LA/resolve/main/Homero-Simpson-LA.zip"], BASE_M, 0),
    "calamardo": ("rvc", [HF + "/EthanRhys/Calamardo-Tentaculos-LA/resolve/main/Calamardo-Tentaculos-LA.zip"], BASE_M, 0),
    "patricio": ("rvc", [HF + "/AmanBOT/Patricio/resolve/main/Patricio.zip"], BASE_M, -2),
    "shrek": ("rvc", [HF + "/bowlql/ShrekLatRVC/resolve/main/shrek-lat.zip"], BASE_M, -2),
    "burro": ("rvc", [HF + "/BrianSalasHache/burro_shrek/resolve/main/burro_shrek.pth"], BASE_M, 2),
    "goku": ("rvc", [HF + "/Robertitohd247/Gokulatino/resolve/main/gokumodel2.0.zip"], BASE_M, 0),
    "loquendo-jorge": ("rvc", [HF + "/legoguy2424/Jorge-Loquendo/resolve/main/Jorge.zip"], BASE_M, 0),
    "loquendo-juan": ("rvc", [HF + "/TheRealheavy/JuanLoquendoRVC/resolve/main/JuanLoquendo.zip"], BASE_M, 0),
    "dross": ("rvc", [HF + "/Slichi/dross/resolve/main/dross.zip"], BASE_M, -2),
    "chavo": ("rvc", [HF + "/Chuckythedoll2005/Voice_Models/resolve/main/ElChavoDelOcho.zip"], BASE_M, 3),
    "don-ramon": ("rvc", [HF + "/IzmaelAguayo/IzmaelAguayoRVC/resolve/main/DonRamon.zip"], BASE_M, 0),
    "duende-verde": ("rvc", [HF + "/coversia21/RVC_DuendeVerde_Latino/resolve/main/jesse_conde.zip"], BASE_M, 0),
}


def _z(path: str, base: str, pitch: int) -> tuple:
    return ("rvc", [HF + "/" + path], base, pitch)


# Más personajes de ficción (modelos RVC de fans en Hugging Face, enlaces verificados nov-2026).
CATALOG.update({
    # --- doblaje latino ---
    "vegeta": _z("Darkame/Vegeta-Rene-Garcia/resolve/main/vegetamodel.zip", BASE_M, 0),
    "bart": _z("AITony70100/BartSimpsonESLA/resolve/main/BartSimpsonESLA_v1_400e.zip", BASE_F, 0),
    "lisa": _z("AITony70100/LisaSimpsonESLA/resolve/main/LisaSimpsonESLA_v2_600e.zip", BASE_F, 2),
    "ralph": _z("AITony70100/RalphWiggum/resolve/main/RalphWiggum_v2.zip", BASE_F, 0),
    "moe": _z("AmanBOT/Moe/resolve/main/Moe.zip", BASE_M, 0),
    "peter-griffin": _z("SkippyLean/PeterGriffinLATs1-s2/resolve/main/PeterGriffinS1-S2.zip", BASE_M, 0),
    "rick": _z("Matius54/Rick_Sanchez_Latino/resolve/main/RVC-v2_Rick_Sanchez_Latino.zip", BASE_M, 0),
    "morty": _z("Matius54/Morty_Smith_Latino/resolve/main/RVC-v2_Morty_Smith_Latino.zip", BASE_M, 5),
    "oogway": _z("Matius54/Maestro_Oogway_Latino/resolve/main/RVC-v2_Maestro_Oogway_Latino.zip", BASE_M, -2),
    "deadpool": _z("AlanOZ/DeadpoolPepeTonoMacias/resolve/main/Deadpool%20-%20Pepe%20To%C3%B1o%20Mac%C3%ADas%20%5BDeadpool%20-%20Latino%20_%20Latin%20American%20Spanish%5D%20-%20Weights%20Model.zip", BASE_M, 0),
    "harley-quinn": _z("EthanRhys/Harley-Quinn-LA/resolve/main/Harley-Quinn-LA.zip", BASE_F, 0),
    "naruto": _z("Darkame/Naruto-Latin-American/resolve/main/Narutomodel.zip", BASE_F, -2),
    "woody": _z("TheRealheavy/WoodyLatinoRVC/resolve/main/WoodyLatino.zip", BASE_M, 0),
    "buzz": _z("Kelpek/BuzzLightyearLatino/resolve/main/BuzzLightyearLatino.zip", BASE_M, 0),
    "don-cangrejo": _z("EthanRhys/Don-Cangrejo-OG/resolve/main/Don-Cangrejo-OG.zip", BASE_M, 0),
    "plankton": _z("AmanBOT/Plankton/resolve/main/Plankton.zip", BASE_M, 3),
    "arenita": _z("EthanRhys/Arenita-Mejillas-LA/resolve/main/Arenita-Mejillas-LA.zip", BASE_F, 0),
    "gru": _z("AmanBOT/Gru/resolve/main/Gru.zip", BASE_M, 0),
    "skipper": _z("AmanBOT/Skipper/resolve/main/Skipper.zip", BASE_M, 0),
    "rey-julien": _z("AmanBOT/Julien/resolve/main/Julien.zip", BASE_M, 3),
    "mojo-jojo": _z("AmanBOT/MojoJojo/resolve/main/MojoJojo.zip", BASE_M, 2),
    "shaggy": _z("AmanBOT/Shaggy/resolve/main/Shaggy.zip", BASE_M, 2),
    "po": _z("AmanBOT/Po/resolve/main/Po.zip", BASE_M, 0),
    "senor-barriga": _z("AmanBOT/SenorBarriga/resolve/main/SenorBarriga.zip", BASE_M, 0),
    "jirafales": _z("AmanBOT/Jirafales/resolve/main/Jirafales.zip", BASE_M, -2),
    "crash": _z("EthanRhys/Crash-Bandicoot-LA/resolve/main/Crash-Bandicoot-LA.zip", BASE_M, 4),
    "optimus": _z("AleXDGoku/optimusprimeespanol/resolve/main/optimusprimeespanol.zip", BASE_M, -3),
    # --- castellano ---
    "doraemon": _z("Gonzaluigi/Doraemon-Esp-RVCv2/resolve/main/Doraemon-ESP-RMVPE-200.zip", BASE_M, 4),
    "shin-chan": _z("Gonzaluigi/Modelos-RVC-Castellano/resolve/main/ShinChan-Castellano-Titan-150.zip", BASE_F, 0),
    "wario": _z("EthanRhys/Wario-Castellano/resolve/main/Wario-Castellano.zip", BASE_M, 0),
    # --- voces sintéticas y otros idiomas (hablarán español con su timbre) ---
    "rin": _z("Miku-chan/KagamineRin/resolve/main/KagamineRin.zip", BASE_F, 4),
    "len": _z("KenmaKIN101/LenKagamineV4_250epochs/resolve/main/LenKagamineV4.zip", BASE_F, 0),
    "luka": _z("aple/MegurineLukaNativeRVC/resolve/main/luka_native_ai.zip", BASE_F, 0),
    "glados": _z("Homiebear/GLaDOSV4/resolve/main/GLaDOS.zip", BASE_F, 0),
    "darth-vader": _z("Homiebear/DarthVaderV4/resolve/main/Darth%20Vader%20V3.zip", BASE_M, -4),
    "mario": _z("EthanRhys/Mario/resolve/main/Mario.zip", BASE_M, 4),
    "luigi": _z("EthanRhys/Luigi/resolve/main/Luigi.zip", BASE_M, 3),
    "sonic": _z("EthanRhys/Sonic-Ryan-Drummond/resolve/main/Sonic-Ryan-Drummond.zip", BASE_M, 3),
    "mickey": _z("Coolwowsocoolwow/Mickey_Mouse/resolve/main/Mickey_Mouse_e160_s3200.zip", BASE_M, 8),
    "pato-donald": _z("Coolwowsocoolwow/Donald_Duck/resolve/main/Donald_Duck_v2.zip", BASE_M, 4),
    "kermit": _z("RosinoSuperRosa/Kermit-The-Frog/resolve/main/kermitthefrogjim.zip", BASE_M, 3),
    "yoda": _z("bowlql/YodaRVC/resolve/main/Yoda.zip", BASE_M, 0),
    "kratos": _z("Homiebear/KratosGoW3/resolve/main/KratosGoW3.zip", BASE_M, -4),
    "master-chief": _z("Homiebear/MasterChief/resolve/main/MasterChief.zip", BASE_M, -2),
    "cartman": _z("LordVessio/eric-cartman-rvc/resolve/main/CartmanClassico.zip", BASE_F, -2),
})


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "streamops-voices/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        while chunk := resp.read(1 << 20):
            buf.write(chunk)
            if total:
                print(f"\r    {buf.tell() / 1048576:6.1f} / {total / 1048576:.1f} MB", end="", flush=True)
        print()
        return buf.getvalue()


def install_piper(name: str, url: str) -> None:
    target = VOICES / f"{name}.onnx"
    if target.is_file() and target.with_suffix(".onnx.json").is_file():
        print(f"  {name}: ya instalada")
        return
    print(f"  {name}: descargando voz Piper")
    target.with_suffix(".onnx.json").write_bytes(fetch(url + ".json"))
    target.write_bytes(fetch(url))


def install_rvc(name: str, urls: list[str], base: str, pitch: int) -> None:
    RVC.mkdir(parents=True, exist_ok=True)
    spec_file = VOICES / f"{name}.voice.json"
    if spec_file.is_file() and (RVC / f"{name}.pth").is_file():
        print(f"  {name}: ya instalada")
        return
    if base in CATALOG:
        install_piper(base, CATALOG[base][1])
    has_index = False
    for url in urls:
        print(f"  {name}: descargando {url.rsplit('/', 1)[-1]}")
        data = fetch(url)
        lower = url.lower().split("?")[0]
        if lower.endswith(".zip"):
            # Solo se extraen .pth/.index, con nombre propio (sin rutas del zip).
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                members = [m for m in archive.infolist() if not m.is_dir()]
                pths = [m for m in members if m.filename.lower().endswith(".pth") and not Path(m.filename).name.startswith(("D_", "G_"))]
                idxs = [m for m in members if m.filename.lower().endswith(".index")]
                if not pths:
                    raise RuntimeError("el zip no contiene un modelo .pth")
                (RVC / f"{name}.pth").write_bytes(archive.read(min(pths, key=lambda m: m.file_size)))
                if idxs:
                    (RVC / f"{name}.index").write_bytes(archive.read(max(idxs, key=lambda m: m.file_size)))
                    has_index = True
        elif lower.endswith(".pth"):
            (RVC / f"{name}.pth").write_bytes(data)
        elif lower.endswith(".index"):
            (RVC / f"{name}.index").write_bytes(data)
            has_index = True
        else:
            raise RuntimeError(f"extensión no reconocida: {url}")
    spec = {"piper": base, "rvc": {"model": f"{name}.pth", "pitch": pitch}}
    # Afinación medida (tools/afinar_voces.py): voz base, tono y velocidad de cada personaje.
    tuning = Path(__file__).with_name("afinacion.json")
    tune = json.loads(tuning.read_text(encoding="utf-8")).get(name) if tuning.is_file() else None
    if tune and (VOICES / f"{tune['piper']}.onnx").is_file():
        spec["piper"], spec["length_scale"], spec["rvc"]["pitch"] = tune["piper"], tune["length_scale"], tune["pitch"]
    if has_index:
        spec["rvc"]["index"] = f"{name}.index"
    spec_file.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(f"  {name}: lista (base {base}, tono {pitch:+d})")


def main(argv: list[str]) -> int:
    VOICES.mkdir(parents=True, exist_ok=True)
    if len(argv) < 2 or argv[1] == "lista":
        print(__doc__)
        for name, entry in CATALOG.items():
            installed = (VOICES / f"{name}.onnx").is_file() or (VOICES / f"{name}.voice.json").is_file()
            print(f"  [{'x' if installed else ' '}] {name:<22} {'Piper' if entry[0] == 'piper' else 'personaje (RVC)'}")
        return 0
    if argv[1] == "instalar":
        names = list(CATALOG) if "todas" in argv[2:] else argv[2:]
        failed = []
        for name in names:
            entry = CATALOG.get(name)
            if entry is None:
                print(f"  {name}: no está en el catálogo")
                failed.append(name)
                continue
            try:
                install_piper(name, entry[1]) if entry[0] == "piper" else install_rvc(name, *entry[1:])
            except Exception as exc:
                print(f"  {name}: ERROR {exc}")
                failed.append(name)
        if failed:
            print("\nFallaron: " + ", ".join(failed))
        return 1 if failed else 0
    if argv[1] == "url" and len(argv) >= 4:
        opts = argv[4:]
        base = opts[opts.index("--base") + 1] if "--base" in opts else BASE_M
        pitch = int(opts[opts.index("--pitch") + 1]) if "--pitch" in opts else 0
        install_rvc(argv[2], [argv[3]], base, pitch)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
