import tempfile
import unittest
from pathlib import Path

from usv_avoidance.nmea_file_source import (
    NmeaFileSource,
    NmeaFrame,
)


AIS_SENTENCE_1 = (
    "!AIVDM,1,1,,A,15Muq?002>G?svP00<:O?vN60<0,0*5C"
)

AIS_SENTENCE_2 = (
    "!AIVDM,1,1,,A,25Muq?002>G?svP00<:O?vN60<0,0*6C"
)

AIS_SENTENCE_3 = (
    "!AIVDO,1,1,,,35Muq?002>G?svP00<:O?vN60<0,0*7C"
)


class NmeaFileSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()

        self.addCleanup(
            self.temporary_directory.cleanup
        )

        self.temp_path = Path(
            self.temporary_directory.name
        )

    def write_source_file(
        self,
        content: str,
    ) -> Path:
        file_path = self.temp_path / "scenario_nmea.txt"

        file_path.write_text(
            content,
            encoding="utf-8",
        )

        return file_path

    def test_read_sentences_keeps_legacy_behavior(self):
        file_path = self.write_source_file(
            "\n".join(
                [
                    "#FRAME,0.0",
                    AIS_SENTENCE_1,
                    AIS_SENTENCE_2,
                    "#FRAME,5.0",
                    AIS_SENTENCE_3,
                    "línea que debe ignorarse",
                ]
            )
        )

        source = NmeaFileSource(str(file_path))

        sentences = list(source.read_sentences())

        self.assertEqual(
            sentences,
            [
                AIS_SENTENCE_1,
                AIS_SENTENCE_2,
                AIS_SENTENCE_3,
            ],
        )

    def test_legacy_file_creates_one_frame_per_sentence(self):
        file_path = self.write_source_file(
            "\n".join(
                [
                    AIS_SENTENCE_1,
                    AIS_SENTENCE_2,
                    AIS_SENTENCE_3,
                ]
            )
        )

        source = NmeaFileSource(str(file_path))

        frames = list(
            source.read_frames(
                default_step_s=5.0,
            )
        )

        self.assertEqual(
            frames,
            [
                NmeaFrame(
                    timestamp_s=0.0,
                    sentences=(AIS_SENTENCE_1,),
                ),
                NmeaFrame(
                    timestamp_s=5.0,
                    sentences=(AIS_SENTENCE_2,),
                ),
                NmeaFrame(
                    timestamp_s=10.0,
                    sentences=(AIS_SENTENCE_3,),
                ),
            ],
        )

    def test_explicit_markers_group_sentences(self):
        file_path = self.write_source_file(
            "\n".join(
                [
                    "#FRAME,0.0",
                    AIS_SENTENCE_1,
                    AIS_SENTENCE_2,
                    "",
                    "#FRAME,5.0",
                    AIS_SENTENCE_3,
                ]
            )
        )

        source = NmeaFileSource(str(file_path))

        frames = list(source.read_frames())

        self.assertEqual(len(frames), 2)

        self.assertEqual(
            frames[0],
            NmeaFrame(
                timestamp_s=0.0,
                sentences=(
                    AIS_SENTENCE_1,
                    AIS_SENTENCE_2,
                ),
            ),
        )

        self.assertEqual(
            frames[1],
            NmeaFrame(
                timestamp_s=5.0,
                sentences=(AIS_SENTENCE_3,),
            ),
        )

    def test_non_ais_lines_are_ignored(self):
        file_path = self.write_source_file(
            "\n".join(
                [
                    "#FRAME,0.0",
                    "comentario de prueba",
                    "$GPGGA,123456,TEST",
                    AIS_SENTENCE_1,
                ]
            )
        )

        source = NmeaFileSource(str(file_path))

        frames = list(source.read_frames())

        self.assertEqual(len(frames), 1)

        self.assertEqual(
            frames[0].sentences,
            (AIS_SENTENCE_1,),
        )

    def test_empty_explicit_frame_is_not_delivered(self):
        file_path = self.write_source_file(
            "\n".join(
                [
                    "#FRAME,0.0",
                    "#FRAME,5.0",
                    AIS_SENTENCE_1,
                ]
            )
        )

        source = NmeaFileSource(str(file_path))

        frames = list(source.read_frames())

        self.assertEqual(
            frames,
            [
                NmeaFrame(
                    timestamp_s=5.0,
                    sentences=(AIS_SENTENCE_1,),
                )
            ],
        )

    def test_invalid_timestamp_raises_value_error(self):
        file_path = self.write_source_file(
            "\n".join(
                [
                    "#FRAME,tiempo_invalido",
                    AIS_SENTENCE_1,
                ]
            )
        )

        source = NmeaFileSource(str(file_path))

        with self.assertRaises(ValueError):
            list(source.read_frames())

    def test_repeated_timestamp_raises_value_error(self):
        file_path = self.write_source_file(
            "\n".join(
                [
                    "#FRAME,5.0",
                    AIS_SENTENCE_1,
                    "#FRAME,5.0",
                    AIS_SENTENCE_2,
                ]
            )
        )

        source = NmeaFileSource(str(file_path))

        with self.assertRaises(ValueError):
            list(source.read_frames())

    def test_decreasing_timestamp_raises_value_error(self):
        file_path = self.write_source_file(
            "\n".join(
                [
                    "#FRAME,10.0",
                    AIS_SENTENCE_1,
                    "#FRAME,5.0",
                    AIS_SENTENCE_2,
                ]
            )
        )

        source = NmeaFileSource(str(file_path))

        with self.assertRaises(ValueError):
            list(source.read_frames())

    def test_default_step_must_be_positive(self):
        file_path = self.write_source_file(
            AIS_SENTENCE_1
        )

        source = NmeaFileSource(str(file_path))

        with self.assertRaises(ValueError):
            list(
                source.read_frames(
                    default_step_s=0.0,
                )
            )

    def test_missing_file_raises_file_not_found(self):
        missing_path = self.temp_path / "missing.txt"

        source = NmeaFileSource(str(missing_path))

        with self.assertRaises(FileNotFoundError):
            list(source.read_frames())


if __name__ == "__main__":
    unittest.main()