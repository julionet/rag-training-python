# Guia de TI — VPN, Acesso e Backup

## Instalação do cliente VPN

O cliente de VPN da Acme Tech é distribuído pelo portal de software e já vem instalado nos notebooks novos. Para instalar manualmente, baixe o pacote do seu sistema operacional, execute o instalador com permissão de administrador e reinicie o computador. Na primeira conexão, informe o endereço do servidor vpn.acmetech.example e use seu usuário corporativo.

A VPN deve ser usada sempre que você acessar sistemas internos fora do escritório. Ela fica desligada automaticamente dentro da rede do escritório, e isso é esperado: não tente conectá-la quando estiver no prédio, pois isso causa lentidão em toda a rede local.

## Autenticação em dois fatores

O acesso à VPN e aos sistemas internos exige um segundo fator de autenticação. Instale o aplicativo autenticador homologado pela empresa e leia o QR code exibido no portal de acesso. Depois disso, a cada conexão você digitará o código de 6 dígitos mostrado no aplicativo, que muda a cada 30 segundos.

Se você trocar de celular, o aplicativo antigo deixa de valer. Abra um chamado de suporte antes de se desfazer do aparelho antigo, pois a redefinição do segundo fator exige a validação de identidade e leva até 48 horas. Quem perde o celular sem aviso fica sem acesso remoto durante esse prazo e deve ir ao escritório para trabalhar.

## Códigos de erro da VPN e do acesso

Os códigos abaixo são os mais comuns e têm solução própria. Os erros E-4021 e E-5107 são tratados no Manual do Colaborador.

| Código | Significado | O que fazer |
|---|---|---|
| V-2210 | Cliente de VPN desatualizado | Atualize o cliente pelo portal de software e tente de novo |
| V-2315 | Limite de dispositivos atingido | Cada usuário pode ter no máximo 2 dispositivos ativos; remova um no portal de acesso |
| S-8800 | Servidor de arquivos indisponível | Aguarde 15 minutos; se persistir, abra um chamado crítico |
| A-1100 | Segundo fator rejeitado | Confira se o horário do celular está automático e gere um novo código |

Antes de abrir um chamado, anote o código exato e o horário do erro. Isso reduz bastante o tempo de atendimento, porque a equipe de TI consegue localizar o registro do problema nos servidores.

## Backup e recuperação de arquivos

O backup dos arquivos da rede acontece todos os dias às 22h e é mantido por 30 dias. Arquivos salvos apenas no disco local do notebook não entram no backup; por isso, grave seus documentos de trabalho na pasta sincronizada com a nuvem corporativa.

Para recuperar um arquivo apagado ou uma versão anterior, abra o portal de backup, escolha a data desejada e solicite a restauração. Pedidos feitos até as 16h costumam ser atendidos em até 4 horas. Pedidos de restauração de mais de 30 dias atrás não são possíveis, porque a cópia já foi descartada.

## Impressoras e equipamentos

A fila de impressão do terceiro andar em São Paulo se chama PRN-SP-02 e atende os times de produto e de engenharia. Para configurar uma impressora nova, abra o painel de impressoras do portal e adicione a fila pelo nome. Toner e papel acabando devem ser reportados pelo mesmo portal, e nunca trocados por conta própria nos equipamentos de locação.

Notebooks são renovados a cada 3 anos. Periféricos como mouse, teclado e headset podem ser solicitados pelo portal e chegam em até 5 dias úteis.
