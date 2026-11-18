# Sega Rally Plus NetLink para Linux — v0.1.1

Recompilação local da edição americana de **Sega Rally Championship Plus NetLink Edition** para Linux x86-64, a partir do disco fornecido pelo jogador. O jogo inicia no modo offline e usa SDL3 para vídeo, áudio e controles.

O velocímetro usa km/h. A corrida amplia o campo de visão nas laterais. O título, os menus, os recordes e os resultados também ocupam a saída 16:9. As ilustrações fixas mantêm suas proporções, com prolongamento do fundo nas laterais. A apresentação intercala imagens completas da corrida para exibição a 60 Hz. A simulação segue a cadência original, próxima de 30 Hz.

O renderizador usa as duas filas de desenho que o jogo reserva para o cenário e os veículos. A versão 0.1.1 corrige a identificação do segundo SH-2, que fazia a primeira fila lotar e deixava trechos de terreno incompletos. As texturas opacas do cenário recebem filtragem quando ficam pequenas à distância.

O Campeonato e a Prática concedem dez segundos adicionais na largada de cada pista, em todas as dificuldades. A partir da segunda etapa do Campeonato, somam-se o saldo anterior, a concessão normal da pista e os dez segundos. Os checkpoints mantêm seus próprios bônus. O jogo continua registrando o tempo real de cada volta.

## Compilar

Use Linux com Python 3.11+, Git, CMake 3.20+, compiladores de C e C++20, Make ou Ninja e os arquivos de desenvolvimento do SDL3 para CMake. Uma imagem CHD também requer o executável `chdman` no PATH. Quem já possui CUE/BIN com um arquivo por faixa pode usá-lo diretamente.

Na pasta do projeto, escolha o comando correspondente à sua imagem.

```sh
python3 build.py "/caminho/jogo.chd" --smoke-test
```

```sh
python3 build.py "/caminho/disco/disc.cue" --smoke-test
```

O processo baixa a revisão fixada do recompilador, verifica os programas do disco e gera o executável dentro de `local/`. A opção `--work` permite escolher outra pasta de trabalho. Para usar uma cópia Git local do recompilador com a revisão indicada abaixo, passe `--upstream /caminho/do/checkout`. A opção `--headless` compila apenas o executável de testes, dispensando o SDL3.

O teste automatizado entra na corrida no deserto, acelera, vira e alterna a câmera. Ao completar 4.000 intervalos de vídeo, deixa duas capturas e o log em `local/smoke/`.

## Jogar no Bazzite

Execute o launcher ou adicione-o ao Steam como jogo externo.

```sh
./local/game/play.sh
```

No Steam, escolha `play.sh` como destino e deixe desativada a opção de forçar uma ferramenta de compatibilidade. Use o layout de gamepad no Steam Input.

| Controle do Ally | Função |
| --- | --- |
| Analógico esquerdo ou direcional | Dirigir e navegar |
| RT ou A | Acelerar |
| LT ou B | Frear |
| X | Alternar câmera |
| RB | Botão C do Saturn, indicado para confirmar nos menus |
| Menu | Start |

As configurações ficam em `game/controls.ini`, o backup do Saturn em `game/saves/cabinet.bup` e o log da sessão em `game/logs/game.log`, dentro da pasta de trabalho. O programa conserva o caminho da imagem usada ao compilar. Para transferi-lo para outro PC Linux compatível, copie a pasta `game` e coloque suas faixas em `game/media/`, com a folha CUE chamada `disc.cue`. Também é possível definir `RALLY_CUE` com o caminho completo da folha CUE no outro aparelho.

## Compatibilidade e licença

A versão 0.1.1 foi testada no ROG Ally com Bazzite. A cobertura inclui Desert, Forest e Mountain em corridas e o modo Time Attack. Multiplayer, modem NetLink e o circuito bônus ainda precisam de testes.

Este projeto usa a revisão `032fd3bc8a6c3e5d23853f53b951aa1446a9dfc1` do saturn-recomp. O repositório distribui scripts de compilação, configuração, endereços de entrada e um patch de código aberto. Você fornece as 17 faixas da sua edição dos EUA. Os arquivos gerados contêm código do jogo e devem permanecer na sua cópia local. As marcas e o jogo pertencem a seus respectivos titulares. A licença MIT abrange o material deste projeto e cada dependência conserva sua própria licença. [Fonte do recompilador](https://github.com/callumjenkins/saturn-recomp/tree/032fd3bc8a6c3e5d23853f53b951aa1446a9dfc1) · [Extração com chdman](https://docs.mamedev.org/tools/chdman.html#extractcd)
