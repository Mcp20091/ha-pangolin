<#
.SYNOPSIS
    List every field the Pangolin Integration API returns, without the values.

.DESCRIPTION
    Calls the list and detail endpoints this integration cares about and
    prints each response's structure: field names and value types only. No
    domains, addresses, emails, keys or names are printed, so the output is
    safe to share in an issue or with a contributor.

    Works in Windows PowerShell 5.1 and PowerShell 7. The API key is asked
    for without being shown (or read from $env:PANGOLIN_API_KEY) and is never
    saved. Endpoints the key can't read are reported as errors and skipped.

.EXAMPLE
    .\scripts\api_fields.ps1 > api-fields.json
#>
param(
    [string]$Url,
    [string]$OrgId,
    [switch]$SkipCertificateCheck
)

$ErrorActionPreference = 'Stop'

function Get-Shape($Value) {
    # Replace every value with its type, keeping the structure.
    if ($null -eq $Value) { return 'null' }
    if ($Value -is [System.Management.Automation.PSCustomObject]) {
        $shape = [ordered]@{}
        foreach ($prop in ($Value.PSObject.Properties | Sort-Object Name)) {
            $shape[$prop.Name] = Get-Shape $prop.Value
        }
        return $shape
    }
    if ($Value -is [System.Collections.IList]) {
        $merged = $null
        foreach ($item in $Value) { $merged = Merge-Shape $merged (Get-Shape $item) }
        if ($null -eq $merged) { return , @() }
        return , @($merged)
    }
    if ($Value -is [bool]) { return 'boolean' }
    # PowerShell 7 turns ISO date strings into DateTime; they're strings in JSON.
    if ($Value -is [datetime] -or $Value -is [string]) { return 'string' }
    if ($Value -is [ValueType]) { return 'number' }
    return 'string'
}

function Merge-Shape($A, $B) {
    # Combine two shapes, so fields seen on any item are listed.
    # The leading comma stops PowerShell unwrapping one-item arrays.
    if ($null -eq $A) { return , $B }
    if ($null -eq $B) { return , $A }
    if ($A -is [System.Collections.IDictionary] -and $B -is [System.Collections.IDictionary]) {
        $merged = [ordered]@{}
        foreach ($key in (@($A.Keys) + @($B.Keys) | Sort-Object -Unique)) {
            $merged[$key] = Merge-Shape $A[$key] $B[$key]
        }
        return $merged
    }
    if ($A -is [array] -and $B -is [array]) {
        $inner = Merge-Shape $(if ($A.Count) { $A[0] }) $(if ($B.Count) { $B[0] })
        if ($null -eq $inner) { return , @() }
        return , @($inner)
    }
    if ($A -is [string] -and $B -is [string] -and $A -eq $B) { return $A }
    $types = @()
    foreach ($side in @($A, $B)) {
        if ($side -is [string]) { $types += $side -split ' \| ' } else { $types += 'object' }
    }
    return (($types | Sort-Object -Unique) -join ' | ')
}

if (-not $Url) { $Url = Read-Host 'Integration API address (e.g. https://api.example.com)' }
if (-not $OrgId) { $OrgId = Read-Host 'Organization ID' }
$OrgId = $OrgId.Trim()
$apiKey = $env:PANGOLIN_API_KEY
if (-not $apiKey) {
    $secure = Read-Host 'API key (not shown)' -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}
$apiKey = $apiKey.Trim()

$base = $Url.Trim().TrimEnd('/')
if (-not $base.EndsWith('/v1')) { $base += '/v1' }
if ($base -notmatch '^https?://') { throw 'The address must start with http:// or https://' }
if ($SkipCertificateCheck -and $PSVersionTable.PSVersion.Major -lt 6) {
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
}

$report = [ordered]@{}

function Invoke-Fetch([string]$Label, [string]$Path, [hashtable]$Query) {
    $uri = $base + $Path
    if ($Query) {
        $pairs = foreach ($entry in $Query.GetEnumerator()) {
            '{0}={1}' -f $entry.Key, [uri]::EscapeDataString([string]$entry.Value)
        }
        $uri += '?' + ($pairs -join '&')
    }
    $request = @{
        Uri        = $uri
        Headers    = @{ Authorization = "Bearer $apiKey" }
        TimeoutSec = 20
    }
    if ($SkipCertificateCheck -and $PSVersionTable.PSVersion.Major -ge 6) {
        $request.SkipCertificateCheck = $true
    }
    try {
        $data = (Invoke-RestMethod @request).data
    }
    catch {
        $code = $null
        try { $code = [int]$_.Exception.Response.StatusCode } catch { $code = $null }
        $report[$Label] = if ($code) { "error $code" } else { "error $($_.Exception.GetType().Name)" }
        return $null
    }
    $report[$Label] = Get-Shape $data
    return $data
}

$null = Invoke-Fetch 'GET /org/{orgId}' "/org/$OrgId"

$lists = @(
    @{ Name = 'sites'; Path = "/org/$OrgId/sites"; Key = 'sites'; Id = 'siteId'; Detail = '/site/{0}'; Extra = @{} },
    @{ Name = 'resources'; Path = "/org/$OrgId/resources"; Key = 'resources'; Id = 'resourceId'; Detail = '/resource/{0}'; Extra = @{} },
    @{ Name = 'private-resources'; Path = "/org/$OrgId/private-resources"; Key = 'siteResources'; Id = 'siteResourceId'; Detail = '/private-resource/{0}'; Extra = @{} },
    @{ Name = 'clients'; Path = "/org/$OrgId/clients"; Key = 'clients'; Id = 'clientId'; Detail = '/client/{0}'; Extra = @{ status = 'active,blocked,archived' } },
    @{ Name = 'user-devices'; Path = "/org/$OrgId/user-devices"; Key = 'devices'; Id = 'clientId'; Detail = '/client/{0}'; Extra = @{ status = 'active,pending,denied,blocked,archived' } }
)

foreach ($list in $lists) {
    $query = @{ page = 1; pageSize = 20 } + $list.Extra
    $label = 'GET ' + $list.Path.Replace("/org/$OrgId", '/org/{orgId}')
    $data = Invoke-Fetch $label $list.Path $query
    $items = @()
    if ($null -ne $data -and $null -ne $data.($list.Key)) { $items = @($data.($list.Key)) }

    # A few items' details are enough to see every field.
    $detailLabel = 'GET ' + ($list.Detail -f '{id}') + " ($($list.Name))"
    foreach ($item in ($items | Select-Object -First 3)) {
        $itemId = $item.($list.Id)
        if ($null -eq $itemId) { continue }
        $previous = $report[$detailLabel]
        $result = Invoke-Fetch $detailLabel ($list.Detail -f $itemId)
        if ($previous -is [System.Collections.IDictionary]) {
            # Keep what earlier items showed, even if this one failed.
            $report[$detailLabel] = if ($null -ne $result) { Merge-Shape $previous $report[$detailLabel] } else { $previous }
        }
    }
    if ($list.Name -eq 'resources' -and $items.Count) {
        $first = $items[0].resourceId
        $null = Invoke-Fetch 'GET /resource/{id}/targets' "/resource/$first/targets"
    }
}

$report | ConvertTo-Json -Depth 30
