# Offline Windows speech -> 32 kHz 16-bit mono WAVs.  Input lines: file|voice|rate|text
param([string]$List, [string]$OutDir)
Add-Type -AssemblyName System.Speech
New-Item -ItemType Directory -Force $OutDir | Out-Null
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(32000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($line in Get-Content $List) {
    if (-not $line.Trim()) { continue }
    $f, $v, $r, $t = $line.Split('|', 4)
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $s.SelectVoice($v); $s.Rate = [int]$r
    $s.SetOutputToWaveFile((Join-Path $OutDir $f), $fmt)
    $s.Speak($t); $s.Dispose()
}
