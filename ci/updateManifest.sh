#!/bin/sh
set -xe

# clone repo manifest
git clone "https://${PERSONAL_ACCESS_TOKEN}@${REPO_MANIFEST_URL}"
cd ./${REPO_MANIFEST_NAME}
git checkout ${REPO_MANIFEST_BRANCH} && git pull

if [ ${GITHUB_REF_NAME} = "standard" ]
then
  echo 'This is standard branch'
  cd ${REPO_MANIFEST_ENV_STANDARD}
else
  exit
fi

# kustomize
curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh"  | bash
./kustomize edit set image ${REPO_MANIFEST_TAG_IMAGE}=${CONTAINER_RELEASE_IMAGE}
rm kustomize

git config --global user.name "${GITHUB_ACTOR}"
git config --global user.email "${GITHUB_ACTOR}@github.com"
git add . 
git commit -m "Update image to ${CONTAINER_RELEASE_IMAGE}"
git push