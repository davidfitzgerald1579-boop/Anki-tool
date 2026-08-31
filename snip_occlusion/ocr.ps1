# OCR an image file using the engine built into Windows 10/11
# (Windows.Media.Ocr) and print the recognized lines to stdout.
# Requires Windows PowerShell 5.x (the WinRT projection used below is not
# available in PowerShell 7); the add-on invokes plain "powershell" which
# is 5.x on every stock Windows install.
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [switch]$Words  # emit one JSON object per word (text + bounding box)
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime

# touch the WinRT types so their assemblies load
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object {
        $_.Name -eq 'AsTask' -and
        $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $null = $netTask.Wait(-1)
    return $netTask.Result
}

$fullPath = (Resolve-Path -LiteralPath $Path).Path
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($fullPath)) `
    ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) `
    ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) `
    ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) `
    ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage(
        [Windows.Globalization.Language]::new("en-GB"))
}
if ($null -eq $engine) {
    Write-Error "No OCR language pack available"
    exit 1
}

$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
if ($Words) {
    $li = 0
    foreach ($line in $result.Lines) {
        foreach ($word in $line.Words) {
            $r = $word.BoundingRect
            $obj = [ordered]@{
                t = $word.Text
                x = [int]$r.X; y = [int]$r.Y
                w = [int]$r.Width; h = [int]$r.Height
                l = $li
            }
            Write-Output (ConvertTo-Json -Compress $obj)
        }
        $li++
    }
} else {
    foreach ($line in $result.Lines) {
        Write-Output $line.Text
    }
}
