export function authDestination(value) {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//") || value.includes(String.fromCharCode(92)) || Array.from(value).some(character => character.charCodeAt(0) < 32) || /^\/auth(?:[/?#]|$)/.test(value)) return null;
  return value;
}

export function loginErrorMessage(error) {
  const response = error && error.response;
  if (response && (response.status === 400 || response.status === 401)) {
    return "COCO Annotatorのユーザー名またはパスワードが正しくありません。check_annotatorとは別のアカウントです。未登録の場合はRegisterから登録してください。";
  }
  return "ログインできませんでした。接続状態を確認して、もう一度お試しください。";
}
