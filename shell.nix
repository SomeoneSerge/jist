with (import <nixpkgs> { });

let
  py = python3.withPackages
    (ps: with ps; [
      nbformat
    ]);
in
mkShell {
  packages = [
    py
    gh
  ];
}
