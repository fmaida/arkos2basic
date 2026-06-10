"""Tests for the command-line interface (cli module)."""

from pathlib import Path

from typer.testing import CliRunner

from arkos2basic.cli import app


EXAMPLE_FILE = Path(__file__).parent.parent / "examples" / "music_01.txt"

runner = CliRunner()


class TestCli:
    """End-to-end tests through the typer application."""

    def test_successful_conversion(self, tmp_path: Path) -> None:
        """A plain run on the example file writes the output file."""
        output = tmp_path / "musica.bas"

        result = runner.invoke(app, [str(EXAMPLE_FILE), str(output)])

        assert result.exit_code == 0
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert content.startswith("musica:")
        assert "DATA BYTE 2" in content


    def test_custom_label(self, tmp_path: Path) -> None:
        """--label changes the music block label."""
        output = tmp_path / "musica.bas"

        result = runner.invoke(
            app, [str(EXAMPLE_FILE), str(output), "--label", "tune"],
        )

        assert result.exit_code == 0
        assert output.read_text(encoding="utf-8").startswith("tune:")


    def test_stop_option(self, tmp_path: Path) -> None:
        """--stop makes the block end with MUSIC STOP."""
        output = tmp_path / "musica.bas"

        result = runner.invoke(app, [str(EXAMPLE_FILE), str(output), "--stop"])

        assert result.exit_code == 0
        content = output.read_text(encoding="utf-8")
        assert content.rstrip().endswith("MUSIC STOP")


    def test_missing_input_file(self, tmp_path: Path) -> None:
        """A non-existing input file is rejected by typer."""
        result = runner.invoke(
            app, [str(tmp_path / "missing.txt"), str(tmp_path / "out.bas")],
        )

        assert result.exit_code != 0


    def test_invalid_data_byte(self, tmp_path: Path) -> None:
        """--data-byte below 1 exits with an error."""
        result = runner.invoke(
            app,
            [str(EXAMPLE_FILE), str(tmp_path / "out.bas"), "--data-byte", "0"],
        )

        assert result.exit_code == 1


    def test_exclude_channels_rejects_non_numeric(self, tmp_path: Path) -> None:
        """A non-numeric --exclude-channels value exits cleanly."""
        result = runner.invoke(
            app,
            [
                str(EXAMPLE_FILE), str(tmp_path / "out.bas"),
                "--exclude-channels", "abc",
            ],
        )

        assert result.exit_code == 1


    def test_exclude_channels_rejects_out_of_range(
        self, tmp_path: Path
    ) -> None:
        """--exclude-channels only accepts 1, 2 or 3."""
        result = runner.invoke(
            app,
            [
                str(EXAMPLE_FILE), str(tmp_path / "out.bas"),
                "--exclude-channels", "5",
            ],
        )

        assert result.exit_code == 1


    def test_exclude_channels_accepts_valid_list(self, tmp_path: Path) -> None:
        """A valid comma-separated list is accepted."""
        output = tmp_path / "out.bas"

        result = runner.invoke(
            app,
            [str(EXAMPLE_FILE), str(output), "--exclude-channels", "2,3"],
        )

        assert result.exit_code == 0
        assert output.exists()
