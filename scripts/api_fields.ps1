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
    saved. The details are checked first, with a retry if they don't work, and
    nothing is saved until they do. Endpoints the key can't read are reported
    as errors and skipped.

    The result is saved as api-fields.json next to this script, and the
    window waits for Enter before closing, so it also works when started
    with right-click > Run with PowerShell.

.EXAMPLE
    .\scripts\api_fields.ps1
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
    # Empty on some items, filled on others: keep the filled structure.
    if ($A -is [string] -and $A -eq 'null' -and ($B -is [System.Collections.IDictionary] -or $B -is [array])) { return , $B }
    if ($B -is [string] -and $B -eq 'null' -and ($A -is [System.Collections.IDictionary] -or $A -is [array])) { return , $A }
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

function Invoke-Call([string]$Path, [hashtable]$Query) {
    # Returns @{ Data = ...; Error = $null } or @{ Data = $null; Error = 'error ...' }.
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
        return @{ Data = (Invoke-RestMethod @request).data; Error = $null }
    }
    catch {
        $code = $null
        try { $code = [int]$_.Exception.Response.StatusCode } catch { $code = $null }
        $message = if ($code) { "error $code" } else { "error $($_.Exception.GetType().Name)" }
        return @{ Data = $null; Error = $message }
    }
}

function Get-Explanation([string]$ErrorText) {
    # Say what went wrong, and whether carrying on could still be useful.
    switch ($ErrorText) {
        'error 401' { return @{ Message = 'The API key was rejected. Check that you copied the whole key.'; CanContinue = $false } }
        'error 403' { return @{ Message = "The key was accepted, but it can't read organization '$OrgId'. Check the organization ID, or give the key the Get Organization permission."; CanContinue = $true } }
        'error 404' { return @{ Message = "Nothing at $base answered like the Pangolin Integration API. Check the address."; CanContinue = $false } }
        default {
            $reason = $ErrorText -replace '^error ', ''
            return @{ Message = "Couldn't reach $base ($reason). Check the address, and that the Integration API is enabled and reachable."; CanContinue = $false }
        }
    }
}

try {
    if ($SkipCertificateCheck -and $PSVersionTable.PSVersion.Major -lt 6) {
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
    }

    # Ask for the details until they work (or the user quits).
    $attempt = 0
    $quit = $false
    $orgResult = $null
    while ($true) {
        $attempt++
        if ($attempt -gt 1 -or -not $Url) {
            # Read-Host would add ": " after the prompt, so print it ourselves.
            Write-Host "Integration API address. Type your domain, or a full http(s):// address if the API isn't on api.<domain>."
            Write-Host -NoNewline 'https://api.'
            $Url = Read-Host
        }
        if ($attempt -gt 1 -or -not $OrgId) { $OrgId = Read-Host 'Organization ID' }
        $OrgId = "$OrgId".Trim()
        if ($attempt -eq 1 -and $env:PANGOLIN_API_KEY) {
            $apiKey = $env:PANGOLIN_API_KEY
        }
        else {
            $secure = Read-Host 'API key (not shown)' -AsSecureString
            $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
            try { $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
            finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
        }
        $apiKey = "$apiKey".Trim()

        $base = "$Url".Trim().TrimEnd('/')
        # The prompt already shows "https://api.", so a bare domain goes after
        # it. A full address is used as typed.
        if ($base -notmatch '://') {
            $base = 'https://' + $(if ($base.StartsWith('api.')) { $base } else { 'api.' + $base })
        }
        if (-not $base.EndsWith('/v1')) { $base += '/v1' }

        $canContinue = $false
        if ($base -notmatch '^https?://') {
            $message = 'The address must start with http:// or https://'
        }
        elseif (-not $apiKey -or -not $OrgId) {
            $message = "The organization ID and API key can't be empty."
        }
        else {
            $orgResult = Invoke-Call "/org/$OrgId" $null
            if (-not $orgResult.Error) { break }
            $explanation = Get-Explanation $orgResult.Error
            $message = $explanation.Message
            $canContinue = $explanation.CanContinue
        }

        Write-Host "`n$message" -ForegroundColor Yellow
        $options = if ($canContinue) { '[R]etry, [C]ontinue anyway, [Q]uit' } else { '[R]etry, [Q]uit' }
        $choice = "$(Read-Host "$options (Enter = retry)")".Trim().ToLower()
        if ($choice -eq 'q') { $quit = $true; break }
        if ($choice -eq 'c' -and $canContinue) { break }
        Write-Host ''
    }

    if ($quit) {
        Write-Host "`nNothing was saved."
    }
    else {
        $report = [ordered]@{}
        $report['GET /org/{orgId}'] = if ($orgResult.Error) { $orgResult.Error } else { Get-Shape $orgResult.Data }

        function Invoke-Fetch([string]$Label, [string]$Path, [hashtable]$Query) {
            $result = Invoke-Call $Path $Query
            $report[$Label] = if ($result.Error) { $result.Error } else { Get-Shape $result.Data }
            return $result.Data
        }

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

            # A few items' details are enough to see every field. Use real IDs
            # from the list; if it couldn't be read, try the first few IDs.
            $ids = @($items | Select-Object -First 3 | ForEach-Object { $_.($list.Id) } | Where-Object { $null -ne $_ })
            $detailLabel = 'GET ' + ($list.Detail -f '{id}') + " ($($list.Name))"
            if ($ids.Count -eq 0) {
                $ids = @(1, 2, 3)
                $detailLabel += ' [guessed IDs 1-3]'
            }
            $merged = $null
            $lastError = $null
            $found = @()
            foreach ($itemId in $ids) {
                $result = Invoke-Call ($list.Detail -f $itemId) $null
                if ($result.Error) { $lastError = $result.Error; continue }
                $merged = Merge-Shape $merged (Get-Shape $result.Data)
                $found += $itemId
            }
            $report[$detailLabel] = if ($null -ne $merged) { $merged } else { $lastError }
            if ($list.Name -eq 'resources') {
                $first = if ($found.Count) { $found[0] } else { $ids[0] }
                $null = Invoke-Fetch 'GET /resource/{id}/targets' "/resource/$first/targets"
            }
        }

        $outFile = Join-Path $PSScriptRoot 'api-fields.json'
        $report | ConvertTo-Json -Depth 30 | Set-Content -Path $outFile -Encoding UTF8
        Write-Host "`nSaved to $outFile"
    }
}
catch {
    Write-Host "`nSomething went wrong: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Nothing was saved.'
}
# Started from Explorer, the window closes as soon as the script ends.
$null = Read-Host "`nPress Enter to close"
