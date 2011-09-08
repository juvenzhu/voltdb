#!/usr/bin/env python

import os, tempfile, sys, shutil
from fabric.api import run, cd, local, get, settings, lcd

builddir = "/tmp/" + os.getenv('USER') + "/buildtemp"
version = "UNKNOWN"

################################################
# USE SSH CONFIG IF POSSIBLE
################################################

def getSSHInfoForHost(host):
    """ Inspired by:
        http://markpasc.typepad.com/blog/2010/04/loading-ssh-config-settings-for-fabric.html """

    from os.path import expanduser
    from paramiko.config import SSHConfig

    key = None
    key_filename = None
    host = host

    def hostinfo(host, config):
        hive = config.lookup(host)
        if 'hostname' in hive:
            host = hive['hostname']
        if 'user' in hive:
            host = '%s@%s' % (hive['user'], host)
        if 'port' in hive:
            host = '%s:%s' % (host, hive['port'])
        return host

    try:
        config_file = file(expanduser('~/.ssh/config'))
    except IOError:
        pass
    else:
        config = SSHConfig()
        config.parse(config_file)
        key = config.lookup(host).get('identityfile', None)
        if key != None: key_filename = expanduser(key)
        host = hostinfo(host, config)
    return key_filename, host

################################################
# CHECKOUT CODE INTO A TEMP DIR
################################################

def checkoutCode(engSvnUrl, proSvnUrl):
    global buildir
    # clean out the existing dir
    run("rm -rf " + builddir)
    # make the build dir again
    run("mkdir -p " + builddir)
    # change to it
    with cd(builddir):
        # do the checkouts
        run("svn co " + engSvnUrl + " eng")
        run("svn co " + proSvnUrl + " pro")
        return run("cat eng/version.txt").strip()

################################################
# MAKE A RELEASE DIR
################################################

def makeReleaseDir(releaseDir):
    # handle the case where a release dir exists for this version
    if os.path.exists(releaseDir):
        if (len(os.listdir(releaseDir)) > 0):
            # make a backup before we clear an existing release dir
            if os.path.exists(releaseDir + ".tgz"):
                os.remove(releaseDir + ".tgz")
            local("tar -czf " +  releaseDir + ".tgz " + releaseDir)
        shutil.rmtree(releaseDir)
    # create a release dir
    os.makedirs(releaseDir)

################################################
# BUILD THE COMMUNITY VERSION
################################################

def buildCommunity():
    with cd(builddir + "/eng"):
        run("pwd")
        run("svn status")
        run("ant clean default dist")

################################################
# BUILD THE ENTERPRISE VERSION
################################################

def buildPro():
    with cd(builddir + "/pro"):
        run("pwd")
        run("svn status")
        run("VOLTCORE=../eng ant -f mmt.xml clean dist.pro")

################################################
# COMPUTE CHECKSUMS
################################################

def copyFilesToReleaseDir(releaseDir, version, operatingsys):
    get("%s/eng/obj/release/voltdb-%s.tar.gz" % (builddir, version),
        "%s/%s-voltdb-%s.tar.gz" % (releaseDir, operatingsys, version))
    get("%s/eng/obj/release/voltdb-client-java-%s.tar.gz" % (builddir, version),
        "%s/voltdb-client-java-%s.tar.gz" % (releaseDir, version))
    get("%s/eng/obj/release/voltdb-studio.web-%s.zip" % (builddir, version),
        "%s/voltdb-studio.web-%s.zip" % (releaseDir, version))
    get("%s/eng/obj/release/voltdb-voltcache-%s.tar.gz" % (builddir, version),
        "%s/%s-voltdb-voltcache-%s.tar.gz" % (releaseDir, operatingsys, version))
    get("%s/eng/obj/release/voltdb-voltkv-%s.tar.gz" % (builddir, version),
        "%s/%s-voltdb-voltkv-%s.tar.gz" % (releaseDir, operatingsys, version))

    # add stripped symbols
    if operatingsys == "LINUX":
        os.makedirs(releaseDir + "/other")
        get("%s/eng/obj/release/voltdb-%s.sym" % (builddir, version),
            "%s/other/%s-voltdb-voltkv-%s.sym" % (releaseDir, operatingsys, version))

    get("%s/pro/obj/pro/voltdb-ent-%s.tar.gz" % (builddir, version),
        "%s/%s-voltdb-ent-%s.tar.gz" % (releaseDir, operatingsys, version))

################################################
# COMPUTE CHECKSUMS
################################################

def computeChecksums(releaseDir):
    md5cmd = "md5sum"
    sha1cmd = "sha1sum"
    if os.uname()[0] == "Darwin":
        md5cmd = "md5 -r"
        sha1cmd = "shasum -a 1"

    with lcd(releaseDir):
        local('echo "CRC checksums:" > checksums.txt')
        local('echo "" >> checksums.txt')
        local('cksum *.*z* >> checksums.txt')
        local('echo "MD5 checksums:" >> checksums.txt')
        local('echo "" >> checksums.txt')
        local('%s *.*z* >> checksums.txt' % md5cmd)
        local('echo "SHA1 checksums:" >> checksums.txt')
        local('echo "" >> checksums.txt')
        local('%s *.*z* >> checksums.txt' % sha1cmd)

################################################
# CREATE CANDIDATE SYMLINKS
################################################

def createCandidateSysmlink(releaseDir):
    candidateDir =  os.getenv('HOME') + "/releases/candidate";
    local("rm -rf " + candidateDir)
    local("ln -s %s %s" % (releaseDir, candidateDir))

################################################
# GET THE SVN URLS TO BUILD THE KIT FROM
################################################

if len(sys.argv) > 3:
    print "usage"

def getSVNURL(defaultPrefix, input):
    input = input.strip()
    if input.startswith("http"):
        return input
    if input[0] == '/':
        input = input[1:]
    return defaultPrefix + input

argv = sys.argv
if len(argv) == 1: argv = ["build-kit.py", "trunk", "branches/rest"]
if len(argv) == 2: argv = ["build-kit.py", argv[0], argv[0]]
eng_svn_url = getSVNURL("https://svn.voltdb.com/eng/", argv[1])
pro_svn_url = getSVNURL("https://svn.voltdb.com/pro/", argv[2])

version = "unknown"

# get ssh config
volt5f = getSSHInfoForHost("volt5f")
voltmini = getSSHInfoForHost("voltmini")

# build kits on 5f
with settings(host_string=volt5f[1],disable_known_hosts=True,key_filename=volt5f[0]):
    version = checkoutCode(eng_svn_url, pro_svn_url)
    print "VERSION: " + version
    buildCommunity()
    buildPro()

# build kits on the mini
with settings(host_string=voltmini[1],disable_known_hosts=True,key_filename=voltmini[0]):
    version2 = checkoutCode(eng_svn_url, pro_svn_url)
    assert version == version2
    buildCommunity()
    buildPro()

releaseDir = os.getenv('HOME') + "/releases/" + version
makeReleaseDir(releaseDir)

# copy kits to the release dir
with settings(host_string=volt5f[1],disable_known_hosts=True,key_filename=volt5f[0]):
    copyFilesToReleaseDir(releaseDir, version, "LINUX")
with settings(host_string=voltmini[1],disable_known_hosts=True,key_filename=voltmini[0]):
    copyFilesToReleaseDir(releaseDir, version, "MAC")

computeChecksums(releaseDir)
createCandidateSysmlink(releaseDir)