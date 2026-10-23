"""The window's texts in English, German, Spanish and Japanese.

English is the default; the language picked with the flags in the window is
kept in the GUI settings.  Each entry holds all translations side by side,
so a new text cannot be added in one language only.
"""

from __future__ import annotations

LANGUAGES = ("en", "de", "es", "ja")
DEFAULT = "en"

_lang = DEFAULT


def set_language(lang: str) -> None:
    global _lang
    _lang = lang if lang in LANGUAGES else DEFAULT


def language() -> str:
    return _lang


def t(key: str, **values) -> str:
    text = TEXTS[key][_lang]
    return text.format(**values) if values else text


def counts(warnings: int, errors: int) -> str:
    """"3 warnings, 1 error" with the right singular and plural."""
    w = t("warning_one" if warnings == 1 else "warning_many", n=warnings)
    e = t("error_one" if errors == 1 else "error_many", n=errors)
    return t("counts", warnings=w, errors=e)


TEXTS: dict[str, dict[str, str]] = {
    # steps: label and hint
    "step_convert": {"en": "Convert", "de": "Konvertieren", "es": "Convertir",
                     "ja": "変換"},
    "step_convert_hint": {"en": "database, maps, events, tilesets and graphics",
                          "de": "Datenbank, Maps, Events, Tilesets und Grafiken",
                          "es": "base de datos, mapas, eventos, tilesets y gráficos",
                          "ja": "データベース、マップ、イベント、タイルセット、画像"},
    "step_transcode": {"en": "Convert audio", "de": "Audio umwandeln",
                       "es": "Convertir audio", "ja": "音声を変換"},
    "step_transcode_hint": {"en": "MIDI, WAV and MP3 to OGG (needs ffmpeg)",
                            "de": "MIDI, WAV und MP3 nach OGG (braucht ffmpeg)",
                            "es": "MIDI, WAV y MP3 a OGG (requiere ffmpeg)",
                            "ja": "MIDI・WAV・MP3 を OGG に（ffmpeg が必要）"},
    "step_fixup": {"en": "Catch missing files", "de": "Fehlende Dateien abfangen",
                   "es": "Corregir archivos que faltan", "ja": "欠けたファイルを補う"},
    "step_fixup_hint": {"en": "blank missing sounds, replace missing images",
                        "de": "fehlende Sounds leeren, fehlende Bilder ersetzen",
                        "es": "vaciar sonidos y sustituir imágenes que faltan",
                        "ja": "無い効果音は空に、無い画像は差し替え"},
    "step_verify": {"en": "Verify", "de": "Prüfen", "es": "Comprobar", "ja": "検証"},
    "step_verify_hint": {"en": "checks that MV/MZ can load the project",
                         "de": "kontrolliert, ob MV/MZ das Projekt laden kann",
                         "es": "comprueba que MV/MZ pueda cargar el proyecto",
                         "ja": "MV/MZ でプロジェクトを読み込めるか確認"},
    "step_package": {"en": "Build game", "de": "Spiel bauen", "es": "Crear juego",
                     "ja": "ゲームを作成"},
    "step_package_hint": {"en": "Game.exe for testing (release from the MZ editor)",
                          "de": "Game.exe zum Testen (veröffentlichen im MZ-Editor)",
                          "es": "Game.exe para pruebas (publica desde el editor de MZ)",
                          "ja": "テスト用 Game.exe（公開は MZ エディタのデプロイメントで）"},

    # text encodings
    "enc_cp1252": {"en": "Western European (English, German, ...)",
                   "de": "Westeuropäisch (Deutsch, Englisch, ...)",
                   "es": "Europa occidental (español, inglés, ...)",
                   "ja": "西ヨーロッパ（英語、ドイツ語など）"},
    "enc_cp932": {"en": "Japanese", "de": "Japanisch", "es": "Japonés", "ja": "日本語"},
    "enc_cp949": {"en": "Korean", "de": "Koreanisch", "es": "Coreano", "ja": "韓国語"},
    "enc_cp936": {"en": "Chinese (simplified)", "de": "Chinesisch (vereinfacht)",
                  "es": "Chino (simplificado)", "ja": "中国語（簡体字）"},
    "enc_cp950": {"en": "Chinese (traditional)", "de": "Chinesisch (traditionell)",
                  "es": "Chino (tradicional)", "ja": "中国語（繁体字）"},
    "enc_cp1251": {"en": "Cyrillic", "de": "Kyrillisch", "es": "Cirílico", "ja": "キリル文字"},
    "enc_cp1250": {"en": "Central European", "de": "Mitteleuropäisch",
                   "es": "Europa central", "ja": "中央ヨーロッパ"},
    "enc_utf-8": {"en": "UTF-8", "de": "UTF-8", "es": "UTF-8", "ja": "UTF-8"},

    # project and template info
    "no_ldb": {"en": "There is no RPG_RT.ldb in this folder.",
               "de": "In diesem Ordner liegt keine RPG_RT.ldb.",
               "es": "En esta carpeta no hay ningún RPG_RT.ldb.",
               "ja": "このフォルダに RPG_RT.ldb がありません。"},
    "engine_2000": {"en": "RPG Maker 2000 (experimental, untested)",
                    "de": "RPG Maker 2000 (experimentell, ungetestet)",
                    "es": "RPG Maker 2000 (experimental, sin probar)",
                    "ja": "RPGツクール2000（実験的・未検証）"},
    "engine_2003": {"en": "RPG Maker 2003", "de": "RPG Maker 2003",
                    "es": "RPG Maker 2003", "ja": "RPGツクール2003"},
    "english_update": {"en": "{version} (official English update)",
                       "de": "{version} (englisches Update)",
                       "es": "{version} (actualización oficial en inglés)",
                       "ja": "{version}（公式英語版アップデート）"},
    "old_version": {"en": "old version", "de": "alte Version", "es": "versión antigua",
                    "ja": "旧バージョン"},
    "reading": {"en": "reading project …", "de": "lese Projekt …",
                "es": "leyendo el proyecto …", "ja": "プロジェクトを読み込み中…"},
    "read_failed": {"en": "Could not read the project: {error}",
                    "de": "Konnte das Projekt nicht lesen: {error}",
                    "es": "No se pudo leer el proyecto: {error}",
                    "ja": "プロジェクトを読み込めませんでした: {error}"},
    "pick_a_game": {"en": "Choose the folder of an RPG Maker 2000/2003 game.",
                    "de": "Wähle den Ordner eines RPG Maker 2000/2003-Spiels.",
                    "es": "Elige la carpeta de un juego de RPG Maker 2000/2003.",
                    "ja": "RPGツクール2000/2003 のゲームのフォルダを選んでください。"},
    "project_counts": {"en": "{maps} maps · {actors} heroes · {events} common events",
                       "de": "{maps} Maps · {actors} Helden · {events} Common Events",
                       "es": "{maps} mapas · {actors} héroes · {events} eventos comunes",
                       "ja": "マップ {maps} · 主人公 {actors} · コモンイベント {events}"},
    "template_none": {"en": "⚠  no template found. ", "de": "⚠  keine Vorlage gefunden. ",
                      "es": "⚠  no se encontró ninguna plantilla. ",
                      "ja": "⚠  テンプレートが見つかりません。"},
    "template_invalid": {"en": "⚠  not an MV/MZ project (js/rmmz_core.js missing). ",
                         "de": "⚠  kein MV/MZ-Projekt (js/rmmz_core.js fehlt). ",
                         "es": "⚠  no es un proyecto de MV/MZ (falta js/rmmz_core.js). ",
                         "ja": "⚠  MV/MZ のプロジェクトではありません（js/rmmz_core.js がありません）。"},
    "template_help": {"en": "Create a new, empty project in RPG Maker MZ and pick its "
                            "folder here. It provides the engine (js/, index.html); "
                            "without it the project does not start and no Game.exe "
                            "is built.",
                      "de": "Lege im RPG Maker MZ ein neues, leeres Projekt an und wähle "
                            "hier dessen Ordner. Daraus kommt die Engine (js/, "
                            "index.html), ohne die das Projekt nicht startet und keine "
                            "Game.exe gebaut wird.",
                      "es": "Crea un proyecto nuevo y vacío en RPG Maker MZ y elige aquí "
                            "su carpeta. De él sale el motor (js/, index.html); sin él "
                            "el proyecto no arranca y no se crea ningún Game.exe.",
                      "ja": "RPGツクールMZ で新しい空のプロジェクトを作り、そのフォルダを"
                            "ここで選んでください。エンジン（js/、index.html）はそこから"
                            "取り込まれます。これが無いとプロジェクトは起動せず、"
                            "Game.exe も作成されません。"},
    "template_mv": {"en": "✓  {label} · a fresh, empty MV project is ideal",
                    "de": "✓  {label} · ein frisches, leeres MV-Projekt ist ideal",
                    "es": "✓  {label} · lo ideal es un proyecto de MV nuevo y vacío",
                    "ja": "✓  {label} · 新しい空の MV プロジェクトが最適です"},
    "template_ok": {"en": "✓  {label} · a fresh, empty MZ project is ideal",
                    "de": "✓  {label} · ein frisches, leeres MZ-Projekt ist ideal",
                    "es": "✓  {label} · lo ideal es un proyecto de MZ nuevo y vacío",
                    "ja": "✓  {label} · 新しい空の MZ プロジェクトが最適です"},
    "tool_ffmpeg": {"en": "ffmpeg (music conversion)", "de": "ffmpeg (Musik umwandeln)",
                    "es": "ffmpeg (conversión de música)", "ja": "ffmpeg（音楽の変換）"},
    "tool_synth": {"en": "FluidSynth (MIDI music)", "de": "FluidSynth (MIDI-Musik)",
                   "es": "FluidSynth (música MIDI)", "ja": "FluidSynth（MIDI 音楽）"},
    "and": {"en": " and ", "de": " und ", "es": " y ", "ja": "と"},
    "tools_missing": {"en": "⚠  {missing} missing – run “{setup}” to install it.",
                      "de": "⚠  {missing} fehlt – starte „{setup}“, um es zu installieren.",
                      "es": "⚠  Falta {missing}: ejecuta «{setup}» para instalarlo.",
                      "ja": "⚠  {missing}がありません。「{setup}」でインストールできます。"},

    # layout
    "support": {"en": "☕  Support", "de": "☕  Unterstützen", "es": "☕  Apoyar",
                "ja": "☕  支援する"},
    "card_game": {"en": "Choose game", "de": "Spiel auswählen", "es": "Elegir juego",
                  "ja": "ゲームを選択"},
    "field_source": {"en": "RM2k project", "de": "RM2k-Projekt", "es": "Proyecto RM2k",
                     "ja": "RM2k プロジェクト"},
    "hint_source": {"en": "the folder with RPG_RT.ldb", "de": "der Ordner mit der RPG_RT.ldb",
                    "es": "la carpeta con RPG_RT.ldb", "ja": "RPG_RT.ldb があるフォルダ"},
    "card_target": {"en": "Destination", "de": "Ziel", "es": "Destino", "ja": "出力先"},
    "field_target": {"en": "MZ project", "de": "MZ-Projekt", "es": "Proyecto MZ",
                     "ja": "MZ プロジェクト"},
    "hint_target": {"en": "the converted project, to open in the editor",
                    "de": "das konvertierte Projekt, zum Öffnen im Editor",
                    "es": "el proyecto convertido, para abrirlo en el editor",
                    "ja": "変換後のプロジェクト（エディタで開けます）"},
    "field_game": {"en": "Game folder", "de": "Spielordner", "es": "Carpeta del juego",
                   "ja": "ゲームフォルダ"},
    "hint_game": {"en": "where the playable version goes (optional)",
                  "de": "hier landet die spielbare Version (optional)",
                  "es": "aquí va la versión jugable (opcional)",
                  "ja": "プレイ可能なゲームの保存先（任意）"},
    "field_template": {"en": "Engine template", "de": "Engine-Vorlage",
                       "es": "Plantilla del motor", "ja": "エンジンのテンプレート"},
    "browse": {"en": "Browse", "de": "Durchsuchen", "es": "Examinar", "ja": "参照"},
    "card_steps": {"en": "Steps", "de": "Schritte", "es": "Pasos", "ja": "手順"},
    "advanced": {"en": "Advanced settings", "de": "Erweiterte Einstellungen",
                 "es": "Opciones avanzadas", "ja": "詳細設定"},
    "encoding": {"en": "Text encoding", "de": "Textkodierung", "es": "Codificación",
                 "ja": "文字コード"},
    "encoding_hint": {"en": "only for games that are not Western European",
                      "de": "nur für Spiele, die nicht westeuropäisch sind",
                      "es": "solo para juegos en otros alfabetos",
                      "ja": "西ヨーロッパ以外の言語のゲームのみ"},
    "field_rtp": {"en": "RTP folder", "de": "RTP-Ordner", "es": "Carpeta RTP",
                  "ja": "RTP フォルダ"},
    "hint_rtp": {"en": "only needed if the RTP is not installed",
                 "de": "nur nötig, wenn das RTP nicht installiert ist",
                 "es": "solo si el RTP no está instalado",
                 "ja": "RTP がインストールされていない場合のみ"},
    "field_soundfont": {"en": "Soundfont", "de": "Soundfont", "es": "SoundFont",
                        "ja": "サウンドフォント"},
    "hint_soundfont": {"en": "sound bank for MIDI music (.sf2/.sf3/.dls)",
                       "de": "Klangbank für MIDI-Musik (.sf2/.sf3/.dls)",
                       "es": "sonidos para música MIDI (.sf2/.sf3/.dls)",
                       "ja": "MIDI 音楽の音色（.sf2/.sf3/.dls）"},
    "run": {"en": "▶  Convert", "de": "▶  Konvertieren", "es": "▶  Convertir",
            "ja": "▶  変換"},
    "ready": {"en": "ready", "de": "bereit", "es": "listo", "ja": "準備完了"},
    "card_log": {"en": "Log", "de": "Protokoll", "es": "Registro", "ja": "ログ"},
    "only_problems": {"en": "only warnings and errors", "de": "nur Warnungen und Fehler",
                      "es": "solo avisos y errores", "ja": "警告とエラーのみ"},
    "copy": {"en": "Copy", "de": "Kopieren", "es": "Copiar", "ja": "コピー"},
    "log_folder": {"en": "Log folder", "de": "Log-Ordner", "es": "Carpeta de registros",
                   "ja": "ログフォルダ"},
    "open_output": {"en": "Open output", "de": "Ausgabe öffnen", "es": "Abrir resultado",
                    "ja": "出力先を開く"},
    "play": {"en": "Start game", "de": "Spiel starten", "es": "Iniciar juego",
             "ja": "ゲームを起動"},

    # small actions
    "open_failed": {"en": "Could not open", "de": "Öffnen fehlgeschlagen",
                    "es": "No se pudo abrir", "ja": "開けませんでした"},
    "not_yet_title": {"en": "Nothing there yet", "de": "Noch nichts da",
                      "es": "Todavía no hay nada", "ja": "まだありません"},
    "not_yet": {"en": "This folder does not exist yet.",
                "de": "Dieser Ordner existiert noch nicht.",
                "es": "Esta carpeta todavía no existe.",
                "ja": "このフォルダはまだ存在しません。"},
    "copied": {"en": "Log copied to the clipboard",
               "de": "Protokoll in die Zwischenablage kopiert",
               "es": "Registro copiado al portapapeles",
               "ja": "ログをクリップボードにコピーしました"},
    "pick_source": {"en": "Folder of the RPG Maker 2000/2003 game (with RPG_RT.ldb)",
                    "de": "Ordner des RPG Maker 2000/2003-Spiels (mit RPG_RT.ldb)",
                    "es": "Carpeta del juego de RPG Maker 2000/2003 (con RPG_RT.ldb)",
                    "ja": "RPGツクール2000/2003 のゲームフォルダ（RPG_RT.ldb があるもの）"},
    "pick_target": {"en": "Destination folder for the MZ project",
                    "de": "Zielordner für das MZ-Projekt",
                    "es": "Carpeta de destino del proyecto MZ",
                    "ja": "MZ プロジェクトの出力先フォルダ"},
    "pick_game": {"en": "Folder for the playable version",
                  "de": "Ordner für die spielbare Version",
                  "es": "Carpeta para la versión jugable",
                  "ja": "プレイ可能なゲームのフォルダ"},
    "pick_template": {"en": "An RPG Maker MZ project as engine template",
                      "de": "Ein RPG Maker MZ-Projekt als Engine-Vorlage",
                      "es": "Un proyecto de RPG Maker MZ como plantilla del motor",
                      "ja": "エンジンのテンプレートにする RPGツクールMZ のプロジェクト"},
    "pick_rtp": {"en": "RTP folder of RPG Maker 2000/2003",
                 "de": "RTP-Ordner von RPG Maker 2000/2003",
                 "es": "Carpeta RTP de RPG Maker 2000/2003",
                 "ja": "RPGツクール2000/2003 の RTP フォルダ"},
    "pick_soundfont": {"en": "Choose a soundfont", "de": "Soundfont wählen",
                       "es": "Elegir un SoundFont", "ja": "サウンドフォントを選択"},
    "all_files": {"en": "All files", "de": "Alle Dateien", "es": "Todos los archivos",
                  "ja": "すべてのファイル"},
    "no_game_title": {"en": "No game yet", "de": "Noch kein Spiel",
                      "es": "Todavía no hay juego", "ja": "ゲームがまだありません"},
    "no_game": {"en": "There is no Game.exe in the game folder yet.\n"
                      "Let the “Build game” step run.",
                "de": "Im Spielordner liegt noch keine Game.exe.\n"
                      "Lass den Schritt „Spiel bauen“ mitlaufen.",
                "es": "En la carpeta del juego todavía no hay ningún Game.exe.\n"
                      "Activa el paso «Crear juego».",
                "ja": "ゲームフォルダにまだ Game.exe がありません。\n"
                      "「ゲームを作成」の手順も実行してください。"},
    "wine_title": {"en": "Wine missing", "de": "Wine fehlt", "es": "Falta Wine",
                   "ja": "Wine がありません"},
    "wine": {"en": "The built game is a Windows application, as RPG Maker MV/MZ "
                   "produces it. On Linux, start it with Wine "
                   "(e.g. “sudo apt install wine”).",
             "de": "Das gebaute Spiel ist eine Windows-Anwendung, wie sie RPG Maker "
                   "MV/MZ erzeugt. Unter Linux startest du es mit Wine "
                   "(z. B. „sudo apt install wine“).",
             "es": "El juego creado es una aplicación de Windows, como las que genera "
                   "RPG Maker MV/MZ. En Linux, ejecútalo con Wine "
                   "(p. ej. «sudo apt install wine»).",
             "ja": "作成されたゲームは、RPGツクールMV/MZ が出力するのと同じ Windows "
                   "アプリです。Linux では Wine で起動してください"
                   "（例:「sudo apt install wine」）。"},

    # running
    "no_source_title": {"en": "No game chosen", "de": "Kein Spiel gewählt",
                        "es": "No se ha elegido ningún juego", "ja": "ゲームが未選択です"},
    "no_source": {"en": "Please choose the folder of an RPG Maker 2000/2003 game "
                        "(the folder with RPG_RT.ldb).",
                  "de": "Bitte den Ordner eines RPG Maker 2000/2003-Spiels wählen "
                        "(der Ordner mit der RPG_RT.ldb).",
                  "es": "Elige la carpeta de un juego de RPG Maker 2000/2003 "
                        "(la carpeta con RPG_RT.ldb).",
                  "ja": "RPGツクール2000/2003 のゲームのフォルダ"
                        "（RPG_RT.ldb があるフォルダ）を選んでください。"},
    "no_target_title": {"en": "No destination", "de": "Kein Ziel", "es": "Sin destino",
                        "ja": "出力先が未指定です"},
    "no_target": {"en": "Please choose a destination folder for the project.",
                  "de": "Bitte einen Zielordner für das Projekt wählen.",
                  "es": "Elige una carpeta de destino para el proyecto.",
                  "ja": "プロジェクトの出力先フォルダを選んでください。"},
    "nothing_title": {"en": "Nothing to do", "de": "Nichts zu tun", "es": "Nada que hacer",
                      "ja": "実行する手順がありません"},
    "nothing": {"en": "Please select at least one step.",
                "de": "Bitte mindestens einen Schritt auswählen.",
                "es": "Selecciona al menos un paso.",
                "ja": "手順を一つ以上選んでください。"},
    "pre_title": {"en": "Requirement missing", "de": "Voraussetzung fehlt",
                  "es": "Falta un requisito", "ja": "必要なものがありません"},
    "pre_template": {"en": "No valid engine template.", "de": "Keine gültige Engine-Vorlage.",
                     "es": "No hay una plantilla del motor válida.",
                     "ja": "有効なエンジンのテンプレートがありません。"},
    "pre_runtime": {"en": "RPG Maker MZ was not found (the nwjs-win folder of its "
                          "installation). Without it, “Build game” cannot create a "
                          "Game.exe.",
                    "de": "RPG Maker MZ wurde nicht gefunden (Ordner nwjs-win der "
                          "Installation). Ohne ihn kann „Spiel bauen“ keine "
                          "Game.exe erzeugen.",
                    "es": "No se encontró RPG Maker MZ (la carpeta nwjs-win de la "
                          "instalación). Sin él, «Crear juego» no puede generar un "
                          "Game.exe.",
                    "ja": "RPGツクールMZ が見つかりません（インストール先の nwjs-win "
                          "フォルダ）。これが無いと「ゲームを作成」で Game.exe を"
                          "作れません。"},
    "pre_continue": {"en": "Continue anyway? The project will then contain only data/ "
                           "and img/ and can neither start nor be built as a game.",
                     "de": "Trotzdem fortfahren? Das Projekt enthält dann nur data/ "
                           "und img/ und lässt sich weder starten noch als Spiel bauen.",
                     "es": "¿Continuar de todos modos? El proyecto solo tendrá data/ e "
                           "img/ y no se podrá iniciar ni crear como juego.",
                     "ja": "それでも続けますか？ プロジェクトには data/ と img/ だけが入り、"
                           "起動もゲームの作成もできません。"},
    "log_skipped": {"en": "“{step}” failed, so these were skipped: {rest}",
                    "de": "„{step}“ fehlgeschlagen, daher übersprungen: {rest}",
                    "es": "«{step}» falló, así que se omitió: {rest}",
                    "ja": "「{step}」が失敗したため、次をスキップしました: {rest}"},
    "log_no_game_dir": {"en": "no game folder given, “Build game” skipped",
                        "de": "kein Spielordner angegeben, „Spiel bauen“ übersprungen",
                        "es": "no se indicó carpeta del juego, se omitió «Crear juego»",
                        "ja": "ゲームフォルダが未指定のため「ゲームを作成」をスキップしました"},
    "step_of": {"en": "Step {n}/{total} · {label}", "de": "Schritt {n}/{total} · {label}",
                "es": "Paso {n}/{total} · {label}", "ja": "手順 {n}/{total} · {label}"},
    "counts": {"en": "{warnings}, {errors}", "de": "{warnings}, {errors}",
               "es": "{warnings}, {errors}", "ja": "{warnings}・{errors}"},
    "warning_one": {"en": "{n} warning", "de": "{n} Warnung", "es": "{n} aviso",
                    "ja": "警告 {n} 件"},
    "warning_many": {"en": "{n} warnings", "de": "{n} Warnungen", "es": "{n} avisos",
                     "ja": "警告 {n} 件"},
    "error_one": {"en": "{n} error", "de": "{n} Fehler", "es": "{n} error",
                  "ja": "エラー {n} 件"},
    "error_many": {"en": "{n} errors", "de": "{n} Fehler", "es": "{n} errores",
                   "ja": "エラー {n} 件"},
    "aborted": {"en": "✗  Aborted after {time} · {counts}",
                "de": "✗  Abgebrochen nach {time} · {counts}",
                "es": "✗  Interrumpido tras {time} · {counts}",
                "ja": "✗  {time} で中断 · {counts}"},
    "done": {"en": "✓  Done in {time} · {counts}", "de": "✓  Fertig in {time} · {counts}",
             "es": "✓  Terminado en {time} · {counts}", "ja": "✓  {time} で完了 · {counts}"},
    "running_title": {"en": "Conversion running", "de": "Konvertierung läuft",
                      "es": "Conversión en curso", "ja": "変換中"},
    "running": {"en": "The conversion is still running. Quit anyway?",
                "de": "Die Konvertierung läuft noch. Trotzdem beenden?",
                "es": "La conversión sigue en curso. ¿Salir de todos modos?",
                "ja": "まだ変換中です。終了してもよろしいですか？"},

    "language_busy": {"en": "The language can be changed once the conversion has finished.",
                      "de": "Die Sprache lässt sich ändern, sobald die Konvertierung fertig ist.",
                      "es": "El idioma se puede cambiar cuando termine la conversión.",
                      "ja": "言語は変換が終わってから切り替えられます。"},

    # support dialog
    "support_title": {"en": "Conversion finished", "de": "Konvertierung abgeschlossen",
                      "es": "Conversión terminada", "ja": "変換が完了しました"},
    "support_head": {"en": "☕  Your game is now an MZ project!",
                     "de": "☕  Dein Spiel ist jetzt ein MZ-Projekt!",
                     "es": "☕  ¡Tu juego ya es un proyecto de MZ!",
                     "ja": "☕  ゲームが MZ プロジェクトになりました！"},
    "support_text": {"en": "MakerBridge is free and open source. If it helped you, I'd be "
                           "glad about a coffee – every coffee goes into more features and "
                           "more games that convert cleanly.",
                     "de": "MakerBridge ist kostenlos und Open Source. Wenn es dir geholfen "
                           "hat, freue ich mich über einen Kaffee – jede Spende fließt in "
                           "weitere Funktionen und noch mehr Spiele, die sauber "
                           "konvertieren.",
                     "es": "MakerBridge es gratuito y de código abierto. Si te ha ayudado, "
                           "me alegraría que me invitaras a un café: cada café se invierte "
                           "en más funciones y en más juegos que se conviertan sin "
                           "problemas.",
                     "ja": "MakerBridge は無料のオープンソースです。お役に立てたなら、"
                           "コーヒー一杯分のご支援をいただけるとうれしいです。"
                           "いただいたご支援は、新しい機能と、より多くのゲームを"
                           "きれいに変換するための開発に使わせていただきます。"},
    "donate": {"en": "☕  Buy me a coffee", "de": "☕  Kaffee spendieren",
               "es": "☕  Invítame a un café", "ja": "☕  コーヒーをおごる"},
    "later": {"en": "Later", "de": "Später", "es": "Más tarde", "ja": "あとで"},
    "never": {"en": "Don't show again", "de": "Nicht mehr anzeigen",
              "es": "No volver a mostrar", "ja": "今後表示しない"},

    "no_window": {"en": "Cannot open a window ({error}). On Linux, python3-tk or a "
                        "graphical session may be missing.",
                  "de": "Kein Fenster möglich ({error}). Unter Linux fehlt vielleicht "
                        "python3-tk oder eine grafische Sitzung.",
                  "es": "No se puede abrir una ventana ({error}). En Linux puede que "
                        "falte python3-tk o una sesión gráfica.",
                  "ja": "ウィンドウを開けません（{error}）。Linux では python3-tk または"
                        "グラフィカルなセッションが無い可能性があります。"},
}

for _key, _entry in TEXTS.items():
    assert set(_entry) == set(LANGUAGES), f"{_key} lacks a translation"
